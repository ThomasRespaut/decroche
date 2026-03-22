# -*- coding: utf-8 -*-
from agents.models import KnowledgeSource, AgentFeedback


FEEDBACK_SOURCE_TITLE = "Corrections utilisateur"
FEEDBACK_SOURCE_TYPE = "text"  # adapte si besoin selon tes choix existants


def build_feedback_knowledge_text(user):
    feedbacks = AgentFeedback.objects.filter(user=user).order_by("created_at")

    parts = []
    for index, item in enumerate(feedbacks, start=1):
        block = [
            f"Correction #{index}",
            f"Canal : {item.get_channel_display()}",
            "",
            "Question utilisateur :",
            item.question or "",
            "",
            "Réponse initiale de l'agent :",
            item.agent_answer or "",
            "",
            "Réponse attendue :",
            item.expected_answer or "",
        ]

        if item.comment:
            block.extend([
                "",
                "Commentaire :",
                item.comment,
            ])

        block.extend([
            "",
            "-" * 70,
            "",
        ])
        parts.append("\n".join(block))

    return "\n".join(parts).strip()


def sync_feedback_knowledge_source(user):
    content = build_feedback_knowledge_text(user)

    source, created = KnowledgeSource.objects.get_or_create(
        user=user,
        title=FEEDBACK_SOURCE_TITLE,
        defaults={
            "source_type": FEEDBACK_SOURCE_TYPE,
            "raw_text": content,
            "extracted_text": content,
            "status": "ready",
            "error_message": "",
        },
    )

    if not created:
        source.raw_text = content
        source.extracted_text = content
        source.status = "ready"
        source.error_message = ""
        source.save(update_fields=[
            "raw_text",
            "extracted_text",
            "status",
            "error_message",
            "updated_at",
        ])

    return source