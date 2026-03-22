from django.utils import timezone

from agents.models import KnowledgeSource, KnowledgeChunk

from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup


# ---------------------------
# TEXT CHUNKING
# ---------------------------
def chunk_text(text, chunk_size=800, overlap=120):
    text = " ".join(text.split())
    chunks = []
    start = 0
    index = 0

    while start < len(text):
        end = start + chunk_size
        content = text[start:end].strip()
        if content:
            chunks.append((index, content))
            index += 1
        start += chunk_size - overlap

    return chunks


# ---------------------------
# WEBSITE SCRAPER
# ---------------------------


def extract_text_from_website(start_url, max_pages=30, max_depth=2):
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    base_netloc = urlparse(start_url).netloc
    visited = set()
    results = []

    queue = deque([(start_url, 0)])

    def normalize_url(current_url, href):
        if not href:
            return None

        href = href.strip()

        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            return None

        absolute_url = urljoin(current_url, href)
        absolute_url, _ = urldefrag(absolute_url)

        parsed = urlparse(absolute_url)

        if parsed.scheme not in ("http", "https"):
            return None

        if parsed.netloc != base_netloc:
            return None

        normalized = parsed._replace(fragment="").geturl().rstrip("/")

        return normalized

    def extract_page_text(html):
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]

        return "\n".join(lines), soup

    while queue and len(visited) < max_pages:
        current_url, depth = queue.popleft()

        normalized_current = current_url.rstrip("/")
        if normalized_current in visited:
            continue

        try:
            response = session.get(current_url, timeout=15)
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                continue

            visited.add(normalized_current)

            page_text, soup = extract_page_text(response.text)

            if page_text:
                results.append(
                    f"\n\n=== PAGE: {current_url} ===\n\n{page_text}"
                )

            if depth >= max_depth:
                continue

            for a_tag in soup.find_all("a", href=True):
                next_url = normalize_url(current_url, a_tag["href"])
                if next_url and next_url not in visited:
                    queue.append((next_url, depth + 1))

        except requests.RequestException:
            continue

    return "\n".join(results).strip()

# ---------------------------
# PDF EXTRACTION
# ---------------------------
def extract_text_from_pdf(path):
    from pypdf import PdfReader

    reader = PdfReader(path)
    parts = []

    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)

    return "\n".join(parts).strip()


def ocr_pdf(path):
    from pdf2image import convert_from_path
    import pytesseract

    images = convert_from_path(path, dpi=200)
    texts = []

    for image in images:
        text = pytesseract.image_to_string(image, lang="fra")
        if text.strip():
            texts.append(text)

    return "\n".join(texts).strip()


def extract_text_from_pdf_source(source):
    pdf_path = source.file.path
    text = extract_text_from_pdf(pdf_path)

    # fallback OCR si texte vide
    if source.use_ocr and len(text.strip()) < 200:
        text = ocr_pdf(pdf_path)

    return text


# ---------------------------
# MAIN PROCESSOR
# ---------------------------
def process_knowledge_source(source_id):
    source = KnowledgeSource.objects.get(id=source_id)

    source.status = "processing"
    source.error_message = ""
    source.save(update_fields=["status", "error_message", "updated_at"])

    try:
        extracted_text = ""

        if source.source_type in ["text", "faq"]:
            extracted_text = source.raw_text or ""

        elif source.source_type == "website":
            extracted_text = extract_text_from_website(source.website_url)

        elif source.source_type == "pdf":
            extracted_text = extract_text_from_pdf_source(source)

        source.extracted_text = extracted_text

        # supprimer anciens chunks
        source.chunks.all().delete()

        chunk_items = chunk_text(extracted_text)

        chunk_objects = [
            KnowledgeChunk(
                source=source,
                chunk_index=index,
                content=content,
                metadata_json=None,
            )
            for index, content in chunk_items
        ]

        KnowledgeChunk.objects.bulk_create(chunk_objects)

        source.chunk_count = len(chunk_objects)
        source.status = "ready"
        source.last_synced_at = timezone.now()

        source.save(update_fields=[
            "extracted_text",
            "chunk_count",
            "status",
            "last_synced_at",
            "updated_at",
        ])

    except Exception as exc:
        source.status = "error"
        source.error_message = str(exc)
        source.save(update_fields=["status", "error_message", "updated_at"])
        raise