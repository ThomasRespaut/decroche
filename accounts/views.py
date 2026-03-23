# -*- coding: utf-8 -*-
import json
import os
import re
import traceback

from openai import OpenAI

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User
from .models import Profile

from agents.models import (
    AgentSettings,
    KnowledgeSource,
    AgentFeedback,
)

from agents.services.knowledge import process_knowledge_source
from agents.services.feedback import sync_feedback_knowledge_source

from .forms import (
    ProfileForm,
    AgentAIForm,
    AgentOptionsForm,
    KnowledgeSourceForm,
    AgentTestMessageForm,
    AgentFeedbackForm,
)

@login_required
def dashboard(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    agent_settings, _ = AgentSettings.objects.get_or_create(user=request.user)

    profile_form = ProfileForm(instance=profile)
    agent_form = AgentAIForm(instance=agent_settings)
    options_form = AgentOptionsForm(instance=agent_settings)
    knowledge_form = KnowledgeSourceForm()
    knowledge_sources = KnowledgeSource.objects.filter(user=request.user).order_by("-created_at")

    if request.method == "POST":
        section = request.POST.get("section")

        if section == "profile":
            profile_form = ProfileForm(request.POST, instance=profile)

            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profil enregistré avec succès.")
                return redirect("dashboard")

            messages.error(request, "Impossible d’enregistrer la section profil.")

        elif section == "ai":
            agent_form = AgentAIForm(request.POST, instance=agent_settings)

            if agent_form.is_valid():
                agent_form.save()
                messages.success(request, "Paramètres IA enregistrés avec succès.")
                return redirect("dashboard")

            messages.error(request, "Impossible d’enregistrer la section IA.")

        elif section == "options":
            options_form = AgentOptionsForm(request.POST, instance=agent_settings)

            if options_form.is_valid():
                options_form.save()
                messages.success(request, "Options enregistrées avec succès.")
                return redirect("dashboard")

            messages.error(request, "Impossible d’enregistrer la section options.")

    context = {
        "profile_form": profile_form,
        "agent_form": agent_form,
        "options_form": options_form,
        "knowledge_form": knowledge_form,
        "knowledge_sources": knowledge_sources,
        "agent": agent_settings,
        "agent_settings": agent_settings,
        "profile": profile,
    }
    return render(request, "dashboard/dashboard.html", context)

@login_required
def add_knowledge_source(request, agent_id):
    print("\n===== ADD KNOWLEDGE SOURCE VIEW =====")
    print("METHOD =", request.method)
    print("agent_id =", agent_id)

    if request.method != "POST":
        print(">>> NOT POST, redirect dashboard")
        return redirect("dashboard")

    print("POST DATA =", dict(request.POST))
    print("FILES =", dict(request.FILES))

    agent_settings = get_object_or_404(
        AgentSettings,
        id=agent_id,
        user=request.user,
    )

    form = KnowledgeSourceForm(request.POST, request.FILES)

    print("form.is_valid() =", form.is_valid())
    if not form.is_valid():
        print("form.errors =", form.errors)
        print("form.non_field_errors =", form.non_field_errors())

        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile_form = ProfileForm(instance=profile)
        agent_form = AgentSettingsForm(instance=agent_settings)
        knowledge_sources = KnowledgeSource.objects.filter(
            user=request.user
        ).order_by("-created_at")[:50]

        messages.error(request, "Impossible d’ajouter la source. Vérifie les champs saisis.")

        return render(
            request,
            "dashboard/dashboard.html",
            {
                "profile_form": profile_form,
                "agent_form": agent_form,
                "knowledge_form": form,
                "knowledge_sources": knowledge_sources,
                "agent": agent_settings,
            },
        )

    source = form.save(commit=False)
    source.user = request.user
    source.status = "pending"
    source.error_message = ""

    print(">>> SOURCE AVANT SAVE")
    print("title =", source.title)
    print("source_type =", source.source_type)
    print("website_url =", source.website_url)
    print("file =", source.file)
    print("raw_text =", (source.raw_text[:200] if source.raw_text else ""))

    source.save()

    print(">>> SOURCE SAVED, ID =", source.id)

    try:
        process_knowledge_source(source.id)
        print(">>> PROCESS OK")
        messages.success(request, "La source a bien été ajoutée et analysée.")
    except Exception as exc:
        print(">>> PROCESS ERROR =", exc)
        source.status = "error"
        source.error_message = str(exc)
        source.save(update_fields=["status", "error_message"])
        messages.warning(
            request,
            f"La source a été enregistrée, mais l’analyse a échoué : {exc}"
        )

    return redirect("dashboard")


@login_required
def update_knowledge_source(request, source_id):
    print("\n===== UPDATE KNOWLEDGE SOURCE VIEW =====")
    print("METHOD =", request.method)
    print("source_id =", source_id)

    if request.method != "POST":
        print(">>> NOT POST, redirect dashboard")
        return redirect("dashboard")

    print("POST DATA =", dict(request.POST))

    source = get_object_or_404(
        KnowledgeSource,
        id=source_id,
        user=request.user,
    )

    edited_text = (request.POST.get("edited_text") or "").strip()
    print("edited_text length =", len(edited_text))

    if not edited_text:
        messages.warning(request, "Le contenu est vide. Rien n’a été enregistré.")
        return redirect("dashboard")

    source.raw_text = edited_text
    source.extracted_text = edited_text
    source.source_type = "text"
    source.status = "pending"
    source.error_message = ""
    source.save()

    print(">>> SOURCE UPDATED, deleting chunks")
    if hasattr(source, "chunks"):
        source.chunks.all().delete()

    try:
        process_knowledge_source(source.id)
        print(">>> REPROCESS OK")
        messages.success(request, "La source a bien été mise à jour et réanalysée.")
    except Exception as exc:
        print(">>> REPROCESS ERROR =", exc)
        source.status = "error"
        source.error_message = str(exc)
        source.save(update_fields=["status", "error_message"])
        messages.warning(
            request,
            f"La source a été enregistrée, mais l’analyse a échoué : {exc}"
        )

    return redirect("dashboard")


@login_required
def delete_knowledge_source(request, source_id):
    print("\n===== DELETE KNOWLEDGE SOURCE VIEW =====")
    print("METHOD =", request.method)
    print("source_id =", source_id)

    if request.method != "POST":
        print(">>> NOT POST, redirect dashboard")
        return redirect("dashboard")

    source = get_object_or_404(
        KnowledgeSource,
        id=source_id,
        user=request.user,
    )

    print(">>> DELETING SOURCE", source.id, source.title)
    source.delete()
    messages.success(request, "La source a bien été supprimée.")
    return redirect("dashboard")


@login_required
def export_knowledge_source(request, source_id):
    source = get_object_or_404(
        KnowledgeSource,
        id=source_id,
        user=request.user,
    )

    content = (
        source.extracted_text
        or source.raw_text
        or ""
    )

    safe_title = (source.title or f"source_{source.id}").replace('"', "").replace("/", "-")
    filename = f"{safe_title}.txt"

    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def export_knowledge_sources(request, agent_id):
    agent_settings = get_object_or_404(
        AgentSettings,
        id=agent_id,
        user=request.user,
    )

    sources = KnowledgeSource.objects.filter(
        user=request.user
    ).order_by("-created_at")

    parts = []

    for source in sources:
        parts.append("=" * 90)
        parts.append(f"TITRE : {source.title or 'Sans titre'}")
        parts.append(f"TYPE : {source.get_source_type_display()}")
        parts.append(f"STATUT : {source.get_status_display()}")

        if source.website_url:
            parts.append(f"URL : {source.website_url}")

        parts.append(f"OCR : {'Oui' if source.use_ocr else 'Non'}")
        parts.append(f"CHUNKS : {source.chunk_count}")
        parts.append(f"PAGES : {source.page_count}")

        if source.last_synced_at:
            parts.append(
                f"DERNIÈRE ANALYSE : {source.last_synced_at.strftime('%d/%m/%Y %H:%M')}"
            )

        if source.error_message:
            parts.append(f"ERREUR : {source.error_message}")

        parts.append("")
        parts.append("CONTENU :")
        parts.append(
            source.extracted_text
            or source.raw_text
            or ""
        )
        parts.append("")
        parts.append("")

    content = "\n".join(parts) if parts else "Aucune source disponible."

    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="toutes_les_sources_rag.txt"'
    return response


def normalize_knowledge_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\n\s+\n", "\n\n", text)

    return text.strip()


@require_POST
@login_required
def clean_knowledge_sources(request, agent_id):
    agent = get_object_or_404(
        AgentSettings,
        id=agent_id,
        user=request.user,
    )
    sources = KnowledgeSource.objects.filter(user=agent.user)

    updated_count = 0

    for source in sources:
        fields_to_update = []

        original_raw_text = source.raw_text or ""
        original_extracted_text = source.extracted_text or ""

        cleaned_raw_text = normalize_knowledge_text(original_raw_text)
        cleaned_extracted_text = normalize_knowledge_text(original_extracted_text)

        if cleaned_raw_text != original_raw_text:
            source.raw_text = cleaned_raw_text
            fields_to_update.append("raw_text")

        if cleaned_extracted_text != original_extracted_text:
            source.extracted_text = cleaned_extracted_text
            fields_to_update.append("extracted_text")

        if fields_to_update:
            source.save(update_fields=fields_to_update)
            updated_count += 1

    if updated_count:
        messages.success(
            request,
            f"Nettoyage terminé : {updated_count} source(s) ont été mises à jour."
        )
    else:
        messages.info(
            request,
            "Aucune source n’avait besoin d’être nettoyée."
        )

    return redirect("dashboard")


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate_for_model(text: str, max_chars: int = 120000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _extract_response_text(response) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()

    try:
        parts = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text_value = getattr(content, "text", None)
                if text_value:
                    parts.append(text_value)
        return "\n".join(parts).strip()
    except Exception:
        return ""


def _optimize_text_for_rag(original_text: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY manquante.")

    model = (
        os.getenv("OPENAI_TEXT_MODEL")
        or getattr(settings, "OPENAI_TEXT_MODEL", None)
        or "gpt-4.1-mini"
    )

    cleaned_input = _truncate_for_model(_normalize_whitespace(original_text))
    client = OpenAI(api_key=api_key)

    developer_prompt = """
Tu es un expert en préparation de connaissances pour moteur RAG, embeddings et recherche sémantique.

Ta mission :
- corriger les erreurs évidentes d’extraction,
- supprimer le bruit inutile,
- conserver les informations métier importantes,
- restructurer le contenu pour améliorer la recherche vectorielle,
- ne jamais inventer d’informations,
- garder un style clair, neutre et exploitable par une IA.

Règles :
1. Conserver les faits, noms propres, horaires, prix, conditions, procédures, FAQ, services, adresses, emails, téléphones.
2. Supprimer au maximum les menus, répétitions, fragments incohérents et parasites.
3. Réorganiser avec des sections explicites quand c’est pertinent.
4. Reformuler légèrement pour clarifier, sans résumer excessivement.
5. Retourner uniquement le texte final optimisé.
"""

    user_prompt = f"""Voici le texte à optimiser pour la base de connaissance :

{cleaned_input}
"""

    response = client.responses.create(
        model=model,
        input=[
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    optimized_text = _extract_response_text(response)
    optimized_text = _normalize_whitespace(optimized_text)

    if not optimized_text:
        raise RuntimeError("La réponse IA est vide.")

    return optimized_text


@require_POST
@login_required
def optimize_knowledge_source(request, source_id):
    try:
        source = get_object_or_404(
            KnowledgeSource,
            id=source_id,
            user=request.user,
        )

        original_text = (
            source.extracted_text
            or source.raw_text
            or ""
        ).strip()

        if not original_text:
            messages.error(request, "Aucun texte à optimiser pour cette source.")
            return redirect("dashboard")

        optimized_text = _optimize_text_for_rag(original_text)

        source.raw_text = optimized_text
        source.extracted_text = optimized_text
        source.source_type = "text"
        source.status = "pending"
        source.error_message = ""
        source.save()

        if hasattr(source, "chunks"):
            source.chunks.all().delete()

        try:
            process_knowledge_source(source.id)
            messages.success(
                request,
                "La source a été optimisée par l’IA puis réanalysée pour améliorer la base documentaire."
            )
        except Exception as exc:
            source.status = "error"
            source.error_message = str(exc)
            source.save(update_fields=["status", "error_message"])
            messages.warning(
                request,
                f"La source a bien été optimisée, mais la réanalyse a échoué : {exc}"
            )

        return redirect("dashboard")

    except Exception as exc:
        print("=== ERREUR optimize_knowledge_source ===")
        print(str(exc))
        traceback.print_exc()

        messages.error(request, f"Erreur lors de l’optimisation IA : {exc}")
        return redirect("dashboard")


@login_required
@require_POST
def preview_voice(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Requête invalide."}, status=400)

    voice = (payload.get("voice") or "").strip()
    text = (payload.get("text") or "").strip()

    if not voice:
        return JsonResponse({"error": "Voix manquante."}, status=400)

    if not text:
        text = "Bonjour, je suis votre assistant vocal."

    api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        return JsonResponse({"error": "OPENAI_API_KEY manquante."}, status=500)

    try:
        client = OpenAI(api_key=api_key)

        speech_response = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text,
        )

        audio_bytes = speech_response.read()

        return HttpResponse(
            audio_bytes,
            content_type="audio/mpeg"
        )

    except Exception as e:
        return JsonResponse(
            {"error": f"Erreur lors de la génération audio : {str(e)}"},
            status=500
        )

# -*- coding: utf-8 -*-
import os
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from openai import OpenAI

from .forms import AgentFeedbackForm, AgentTestMessageForm
from .models import Profile
from agents.models import (
    AgentFeedback,
    AgentSettings,
    BusinessProfile,
    FrequentlyAskedQuestion,
    AgentTool,
    KnowledgeSource,
)
from agents.services.feedback import sync_feedback_knowledge_source


def _safe_getattr(obj, attr_names):
    for attr in attr_names:
        if obj and hasattr(obj, attr):
            value = getattr(obj, attr)
            if value:
                return value
    return ""


def _decode_unicode_escapes_only(text: str) -> str:
    if not text:
        return ""

    text = str(text)

    # plusieurs passes pour gérer:
    # \u000A
    # \\u000A
    # \\\\u000A
    for _ in range(3):
        new_text = re.sub(
            r"\\u([0-9a-fA-F]{4})",
            lambda m: chr(int(m.group(1), 16)),
            text,
        )
        new_text = new_text.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")

        if new_text == text:
            break
        text = new_text

    return text


def _fix_common_mojibake(text: str) -> str:
    if not text:
        return ""

    text = str(text)

    suspicious_markers = ("Ã", "â", "€", "™", "œ", "�")
    if not any(marker in text for marker in suspicious_markers):
        return text

    candidates = []

    try:
        candidates.append(text.encode("latin1").decode("utf-8"))
    except Exception:
        pass

    try:
        candidates.append(text.encode("cp1252").decode("utf-8"))
    except Exception:
        pass

    def score(s: str) -> int:
        bad = ("Ã", "â", "€", "™", "�")
        return sum(s.count(x) for x in bad)

    if candidates:
        best = min(candidates, key=score)
        if score(best) < score(text):
            return best

    return text


def clean_ai_text(text: str) -> str:
    if text is None:
        return ""

    text = str(text)

    # normalisation
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # décode \u000A, \u002D, \n, etc. même si doublement échappés
    text = _decode_unicode_escapes_only(text)

    # corrige le mojibake éventuel
    text = _fix_common_mojibake(text)

    # nettoyage général
    text = text.replace("\u0000", "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()

def clean_ai_text(text: str) -> str:
    if text is None:
        return ""

    text = str(text)

    # normalisation des retours ligne
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # décode uniquement les \uXXXX littéraux
    text = _decode_unicode_escapes_only(text)

    # corrige les textes cassés du type Ã© / â
    text = _fix_common_mojibake(text)

    # nettoyage général
    text = text.replace("\u0000", "")
    text = text.replace("\xa0", " ")

    # espaces multiples
    text = re.sub(r"[ \t]+", " ", text)

    # espaces parasites autour des sauts de ligne
    text = re.sub(r" *\n *", "\n", text)

    # max 2 lignes vides consécutives
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _truncate_text(text, max_chars=12000):
    text = clean_ai_text(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[contenu tronqué]"


def _build_profile_context(profile):
    if not profile:
        return "Aucun profil entreprise fourni."

    fields_map = [
        ("Nom de l’entreprise", ["company_name", "business_name", "name"]),
        ("Activité", ["activity", "sector", "business_type"]),
        ("Description", ["description", "about", "summary"]),
        ("Téléphone", ["phone", "phone_number"]),
        ("Email", ["email", "contact_email"]),
        ("Adresse", ["address"]),
        ("Ville", ["city"]),
        ("Site web", ["website", "website_url"]),
    ]

    lines = []
    for label, attrs in fields_map:
        value = clean_ai_text(_safe_getattr(profile, attrs))
        if value:
            lines.append(f"- {label} : {value}")

    return "\n".join(lines) if lines else "Aucun détail exploitable dans le profil entreprise."


def _build_business_context(user):
    business = BusinessProfile.objects.filter(user=user).first()
    if not business:
        return "Aucun profil business détaillé disponible."

    fields_map = [
        ("Nom entreprise", ["company_name", "business_name", "name"]),
        ("Activité", ["activity_type", "activity", "sector", "business_type"]),
        ("Téléphone", ["phone", "phone_number"]),
        ("Site web", ["website_url", "website"]),
        ("Adresse", ["address"]),
        ("Ville", ["city"]),
        ("Code postal", ["postal_code"]),
        ("Description", ["business_description", "description", "about"]),
        ("Horaires", ["opening_hours"]),
        ("Notes internes", ["extra_notes", "internal_notes"]),
    ]

    lines = []
    for label, attrs in fields_map:
        value = clean_ai_text(_safe_getattr(business, attrs))
        if value:
            lines.append(f"- {label} : {value}")

    return "\n".join(lines) if lines else "Aucune donnée business exploitable."


def _build_agent_settings_context(agent_settings):
    if not agent_settings:
        return "Aucun réglage agent fourni."

    ai_name = clean_ai_text(getattr(agent_settings, "ai_name", "") or "Assistant IA")
    greeting_message = clean_ai_text(getattr(agent_settings, "greeting_message", "") or "")
    system_prompt = clean_ai_text(getattr(agent_settings, "system_prompt", "") or "")
    tone = clean_ai_text(getattr(agent_settings, "tone", "") or "")
    voice = clean_ai_text(getattr(agent_settings, "voice", "") or "")
    language = clean_ai_text(getattr(agent_settings, "language", "") or "fr")
    response_style = clean_ai_text(getattr(agent_settings, "response_style", "") or "")
    fallback_message = clean_ai_text(getattr(agent_settings, "fallback_message", "") or "")

    lines = [
        f"- Nom de l’agent : {ai_name}",
        f"- Tonalité : {tone or 'non définie'}",
        f"- Voix : {voice or 'non définie'}",
        f"- Langue : {language}",
    ]

    if response_style:
        lines.append(f"- Style de réponse : {response_style}")

    if greeting_message:
        lines.append(f"- Message d’accueil : {greeting_message}")

    if fallback_message:
        lines.append(f"- Message fallback : {fallback_message}")

    if system_prompt:
        lines.append("")
        lines.append("Consignes système personnalisées :")
        lines.append(system_prompt)

    return "\n".join(lines)


def _build_faq_context(user, max_items=40):
    faqs = FrequentlyAskedQuestion.objects.filter(user=user, is_active=True)[:max_items]
    if not faqs:
        return "Aucune FAQ active."

    blocks = []
    for idx, faq in enumerate(faqs, start=1):
        question = clean_ai_text(getattr(faq, "question", ""))
        answer = clean_ai_text(getattr(faq, "answer", ""))
        if question or answer:
            blocks.append(f"[FAQ {idx}]\nQ: {question}\nR: {answer}")

    return "\n\n".join(blocks) if blocks else "Aucune FAQ exploitable."


def _build_tools_context(agent_settings):
    if not agent_settings:
        return "Aucun outil actif."

    tools = AgentTool.objects.filter(agent=agent_settings, enabled=True)
    if not tools:
        return "Aucun outil actif."

    return ", ".join(clean_ai_text(t.tool_key) for t in tools if getattr(t, "tool_key", None))


def _build_knowledge_context(knowledge_sources, max_sources=8, max_chars_per_source=6000):
    if not knowledge_sources:
        return "Aucune source documentaire disponible."

    blocks = []
    count = 0

    for source in knowledge_sources:
        if count >= max_sources:
            break

        content = clean_ai_text(
            getattr(source, "extracted_text", None)
            or getattr(source, "raw_text", None)
            or ""
        )

        if not content:
            continue

        title = clean_ai_text(getattr(source, "title", None) or "Source sans titre")
        source_type = clean_ai_text(getattr(source, "source_type", None) or "unknown")
        status = clean_ai_text(getattr(source, "status", None) or "unknown")

        block = [
            f"[SOURCE {count + 1}]",
            f"Titre : {title}",
            f"Type : {source_type}",
            f"Statut : {status}",
            "Contenu :",
            _truncate_text(content, max_chars=max_chars_per_source),
        ]
        blocks.append("\n".join(block))
        count += 1

    if not blocks:
        return "Des sources existent mais aucun texte exploitable n’a été extrait."

    return "\n\n" + ("\n\n" + ("-" * 80) + "\n\n").join(blocks)


def _build_feedback_context(user, max_items=20):
    feedbacks = AgentFeedback.objects.filter(user=user).order_by("-created_at")[:max_items]
    if not feedbacks:
        return "Aucune correction utilisateur disponible."

    blocks = []
    for idx, item in enumerate(feedbacks, start=1):
        question = clean_ai_text(getattr(item, "question", "") or getattr(item, "message", ""))
        agent_answer = clean_ai_text(
            getattr(item, "agent_answer", "") or getattr(item, "wrong_answer", "")
        )
        expected_answer = clean_ai_text(
            getattr(item, "expected_answer", "") or getattr(item, "correct_answer", "")
        )
        comment = clean_ai_text(getattr(item, "comment", "") or "")
        channel = clean_ai_text(getattr(item, "channel", "") or "text")

        block = [
            f"[CORRECTION {idx}]",
            f"Canal : {channel}",
            "Question :",
            question,
            "",
            "Réponse précédente de l’agent :",
            agent_answer,
            "",
            "Réponse attendue :",
            expected_answer,
        ]

        if comment:
            block.extend(["", "Commentaire :", comment])

        blocks.append("\n".join(block))

    return "\n\n".join(blocks)


def _build_chat_history_context(chat_history, max_turns=12):
    if not chat_history:
        return []

    trimmed = chat_history[-max_turns:]
    messages_list = []

    for item in trimmed:
        question = clean_ai_text(item.get("question", ""))
        answer = clean_ai_text(item.get("answer", ""))

        if question:
            messages_list.append({
                "role": "user",
                "content": question,
            })

        if answer:
            messages_list.append({
                "role": "assistant",
                "content": answer,
            })

    return messages_list


def _clean_feedback_instance(feedback):
    """
    Nettoie les champs texte du feedback avant sauvegarde
    pour éviter de stocker des \\u000A, \\u002D, etc.
    """
    text_fields = [
        "message",
        "question",
        "agent_answer",
        "wrong_answer",
        "expected_answer",
        "correct_answer",
        "comment",
    ]

    for field_name in text_fields:
        if hasattr(feedback, field_name):
            value = getattr(feedback, field_name, None)
            if isinstance(value, str) and value:
                setattr(feedback, field_name, clean_ai_text(value))

    return feedback


def generate_agent_test_answer(
    message,
    user=None,
    profile=None,
    agent_settings=None,
    knowledge_sources=None,
    chat_history=None,
):
    api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        return "OPENAI_API_KEY manquante"

    client = OpenAI(api_key=api_key)

    profile_context = _build_profile_context(profile)
    business_context = _build_business_context(user)
    agent_context = _build_agent_settings_context(agent_settings)
    faq_context = _build_faq_context(user)
    tools_context = _build_tools_context(agent_settings)
    feedback_context = _build_feedback_context(user)

    knowledge_context = "RAG désactivé ou aucune base documentaire."
    if agent_settings and getattr(agent_settings, "enable_rag", False):
        knowledge_context = _build_knowledge_context(
            knowledge_sources=knowledge_sources,
            max_sources=5,
            max_chars_per_source=4000,
        )

    history_messages = _build_chat_history_context(chat_history, max_turns=6)

    ai_name = clean_ai_text(getattr(agent_settings, "ai_name", "") or "Assistant IA")
    language = clean_ai_text(getattr(agent_settings, "language", "") or "fr")
    tone = clean_ai_text(getattr(agent_settings, "tone", "") or "chaleureux")
    response_style = clean_ai_text(
        getattr(agent_settings, "response_style", "") or "Réponses courtes, naturelles et rassurantes"
    )
    fallback_message = clean_ai_text(
        getattr(agent_settings, "fallback_message", "") or "Je n’ai pas cette information pour le moment."
    )
    custom_system_prompt = clean_ai_text(getattr(agent_settings, "system_prompt", "") or "")

    system_prompt = f"""
Tu es {ai_name}, un agent vocal d'entreprise.

Langue : {language}
Ton : {tone}
Style : {response_style}

Comportement attendu :
- Réponses naturelles, fluides et professionnelles
- Réponses plutôt courtes
- Une information fausse ne doit jamais être inventée
- Utiliser en priorité : corrections utilisateur > FAQ > base documentaire > profil entreprise
- Si une information manque, utiliser le message fallback ou proposer de transmettre la demande
- Ne jamais afficher de séquences techniques comme \\u000A, \\u002D, \\n, \\t ou toute autre séquence d’échappement
- Toujours répondre dans un français propre, lisible et naturel

Fonctionnalités actives :
- Prise RDV : {getattr(agent_settings, "enable_appointment_booking", False)}
- Transfert humain : {getattr(agent_settings, "enable_human_transfer", False)}
- SMS suivi : {getattr(agent_settings, "enable_sms_followup", False)}

Message fallback :
{fallback_message}

Consignes personnalisées :
{custom_system_prompt}
""".strip()

    developer_prompt = f"""
RÉGLAGES AGENT
{agent_context}

PROFIL ENTREPRISE
{profile_context}

PROFIL BUSINESS DÉTAILLÉ
{business_context}

FAQ
{faq_context}

CORRECTIONS UTILISATEUR
{feedback_context}

OUTILS ACTIFS
{tools_context}

BASE DOCUMENTAIRE
{knowledge_context}
""".strip()

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "developer", "content": developer_prompt},
                *history_messages,
                {"role": "user", "content": clean_ai_text(message)},
            ],
            text={"format": {"type": "text"}},
        )

        raw_text = response.output_text or ""
        return clean_ai_text(raw_text)

    except Exception as e:
        return clean_ai_text(f"Erreur OpenAI: {str(e)}")


@login_required
def test_agent(request):
    profile = Profile.objects.filter(user=request.user).first()
    agent_settings = AgentSettings.objects.filter(user=request.user).first()
    knowledge_sources = KnowledgeSource.objects.filter(user=request.user).order_by("-created_at")
    feedbacks = AgentFeedback.objects.filter(user=request.user).order_by("-created_at")[:10]

    test_form = AgentTestMessageForm()
    feedback_form = AgentFeedbackForm(
        initial={
            "channel": "text",
        }
    )

    raw_chat_history = request.session.get("agent_test_chat_history", [])
    chat_history = [
        {
            "question": clean_ai_text(item.get("question", "")),
            "answer": clean_ai_text(item.get("answer", "")),
        }
        for item in raw_chat_history
        if isinstance(item, dict)
    ]

    if chat_history != raw_chat_history:
        request.session["agent_test_chat_history"] = chat_history
        request.session.modified = True

    scenario_prompts = [
        "Bonjour, quels sont vos horaires ?",
        "Pouvez-vous me donner vos tarifs ?",
        "Je voudrais prendre rendez-vous.",
        "Faites-vous de la livraison ?",
        "Je souhaite parler à un humain.",
    ]

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        if action == "test_message":
            test_form = AgentTestMessageForm(request.POST)
            if test_form.is_valid():
                user_message = clean_ai_text(test_form.cleaned_data.get("message", ""))

                if user_message:
                    agent_answer = generate_agent_test_answer(
                        message=user_message,
                        user=request.user,
                        profile=profile,
                        agent_settings=agent_settings,
                        knowledge_sources=knowledge_sources,
                        chat_history=chat_history,
                    )
                    agent_answer = clean_ai_text(agent_answer)

                    chat_history.append({
                        "question": user_message,
                        "answer": agent_answer,
                    })

                    request.session["agent_test_chat_history"] = chat_history
                    request.session.modified = True

                    messages.success(request, "Message de test envoyé à l’agent.")
                    return redirect("test_agent")

        elif action == "scenario_message":
            scenario_message = clean_ai_text(request.POST.get("scenario_message", ""))
            if scenario_message:
                agent_answer = generate_agent_test_answer(
                    message=scenario_message,
                    user=request.user,
                    profile=profile,
                    agent_settings=agent_settings,
                    knowledge_sources=knowledge_sources,
                    chat_history=chat_history,
                )
                agent_answer = clean_ai_text(agent_answer)

                chat_history.append({
                    "question": scenario_message,
                    "answer": agent_answer,
                })

                request.session["agent_test_chat_history"] = chat_history
                request.session.modified = True

                messages.success(request, "Scénario lancé.")
                return redirect("test_agent")

        elif action == "save_feedback":
            cleaned_post = _clean_posted_feedback_data(request.POST)
            feedback_form = AgentFeedbackForm(cleaned_post)

            if feedback_form.is_valid():
                feedback = feedback_form.save(commit=False)
                feedback.user = request.user
                feedback = _clean_feedback_instance(feedback)
                feedback.save()

                sync_feedback_knowledge_source(request.user)

                messages.success(
                    request,
                    "Correction enregistrée et ajoutée à la source de connaissance dédiée."
                )
                return redirect("test_agent")

                sync_feedback_knowledge_source(request.user)

                messages.success(
                    request,
                    "Correction enregistrée et ajoutée à la source de connaissance dédiée."
                )
                return redirect("test_agent")

        elif action == "reset_chat":
            request.session["agent_test_chat_history"] = []
            request.session.modified = True
            messages.success(request, "Historique de test réinitialisé.")
            return redirect("test_agent")

    cleaned_feedbacks = []
    for item in feedbacks:
        for field_name in [
            "message",
            "question",
            "agent_answer",
            "wrong_answer",
            "expected_answer",
            "correct_answer",
            "comment",
        ]:
            if hasattr(item, field_name):
                value = getattr(item, field_name, None)
                if isinstance(value, str):
                    setattr(item, field_name, clean_ai_text(value))
        cleaned_feedbacks.append(item)

    context = {
        "profile": profile,
        "agent_settings": agent_settings,
        "knowledge_sources": knowledge_sources,
        "feedbacks": cleaned_feedbacks,
        "test_form": test_form,
        "feedback_form": feedback_form,
        "chat_history": chat_history,
        "scenario_prompts": scenario_prompts,
    }
    return render(request, "dashboard/test_agent.html", context)


def _clean_posted_feedback_data(post_data):
    data = post_data.copy()

    possible_fields = [
        "message",
        "question",
        "agent_answer",
        "wrong_answer",
        "expected_answer",
        "correct_answer",
        "comment",
    ]

    for field in possible_fields:
        if field in data:
            data[field] = clean_ai_text(data.get(field, ""))

    return data



