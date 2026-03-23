# agents/services/prompt_builder.py
from agents.models import FrequentlyAskedQuestion, KnowledgeSource


def _format_activity_label(activity_type: str) -> str:
    mapping = {
        "restaurant": "Restaurant",
        "medical": "Cabinet médical",
        "beauty": "Beauté / Bien-être",
        "real_estate": "Immobilier",
        "lawyer": "Cabinet juridique",
        "plumber": "Plomberie",
        "electrician": "Électricité",
        "retail": "Commerce",
        "agency": "Agence",
        "other": "Autre",
    }
    return mapping.get(activity_type, activity_type or "Autre")


def build_agent_system_prompt(agent, business_profile=None, knowledge_limit=12000):
    """
    Construit le prompt système temps réel à partir de la configuration existante.
    """

    language_instruction = {
        "fr": "Tu dois répondre exclusivement en français.",
        "en": "You must answer exclusively in English.",
    }.get(agent.language, "Tu dois répondre exclusivement en français.")

    tone_instruction = {
        "professionnel": "Ton ton est professionnel, clair et rassurant.",
        "chaleureux": "Ton ton est chaleureux, humain et accueillant.",
        "dynamique": "Ton ton est dynamique, fluide et engageant.",
        "premium": "Ton ton est haut de gamme, élégant et très soigné.",
        "rassurant": "Ton ton est calme, rassurant et posé.",
        "direct": "Ton ton est direct, simple et efficace.",
    }.get(agent.tone, "Ton ton est professionnel.")

    parts = [
        f"Tu t'appelles {agent.ai_name}.",
        language_instruction,
        tone_instruction,
        f"Style de réponse attendu : {agent.response_style}",
        "Tu es un agent téléphonique vocal en temps réel.",
        "Tu réponds comme un vrai collaborateur de l'entreprise, naturellement, sans dire que tu lis une base de données.",
        "Tu fais des réponses courtes et conversationnelles adaptées au téléphone.",
        "Tu ne fais pas de longues listes sauf nécessité absolue.",
        "Si l'utilisateur parle de manière imprécise, tu aides avec tact.",
        f"Message d'accueil conseillé : {agent.greeting_message}",
        f"Message de secours si l'information manque : {agent.fallback_message}",
    ]

    if agent.interruptible:
        parts.append(
            "L'appelant peut t'interrompre à tout moment. Quand il parle, tu t'arrêtes et tu écoutes."
        )

    if agent.max_call_duration_seconds:
        parts.append(
            f"Tu dois rester efficace car la durée cible maximale d'appel est de {agent.max_call_duration_seconds} secondes."
        )

    if business_profile:
        parts.extend([
            "",
            "=== ENTREPRISE ===",
            f"Nom : {business_profile.company_name or ''}",
            f"Activité : {_format_activity_label(business_profile.activity_type)}",
            f"Téléphone : {business_profile.phone or ''}",
            f"Site web : {business_profile.website_url or ''}",
            f"Description : {business_profile.business_description or ''}",
            f"Horaires : {business_profile.opening_hours or ''}",
            f"Adresse : {business_profile.address or ''}",
            f"Ville : {business_profile.city or ''}",
            f"Code postal : {business_profile.postal_code or ''}",
            f"Notes internes : {business_profile.extra_notes or ''}",
        ])

    parts.extend([
        "",
        "=== RÈGLES MÉTIER ===",
        "Quand tu connais une information fiable, tu réponds directement.",
        "Quand l'information n'est pas certaine, tu le dis honnêtement.",
        "Tu ne dois jamais inventer un horaire, un prix, une disponibilité ou une procédure.",
        "Si tu ne sais pas, tu proposes de prendre un message.",
    ])

    if agent.enable_appointment_booking:
        parts.append("Tu peux proposer la prise de rendez-vous si le besoin s'y prête.")

    if agent.enable_table_booking:
        parts.append("Tu peux aider à gérer une réservation de table si l'activité le justifie.")

    if agent.enable_human_transfer:
        parts.append("Si nécessaire, tu peux proposer un transfert vers un humain ou une demande de rappel.")

    if agent.enable_sms_followup:
        parts.append("Tu peux proposer qu'un SMS de suivi soit envoyé après l'appel si nécessaire.")

    if agent.system_prompt:
        parts.extend([
            "",
            "=== CONSIGNES PERSONNALISÉES ===",
            agent.system_prompt.strip(),
        ])

    faqs = FrequentlyAskedQuestion.objects.filter(
        user=agent.user,
        is_active=True,
    ).order_by("sort_order", "id")

    faq_texts = []
    for faq in faqs:
        faq_texts.append(f"Q: {faq.question}\nR: {faq.answer}")

    if faq_texts:
        parts.extend([
            "",
            "=== FAQ ===",
            "\n\n".join(faq_texts),
        ])

    if agent.enable_rag:
        sources = KnowledgeSource.objects.filter(
            user=agent.user,
            status="ready",
        ).order_by("-updated_at")

        knowledge_blocks = []
        total_len = 0

        for source in sources:
            text = (source.extracted_text or source.raw_text or "").strip()
            if not text:
                continue

            title = source.title or source.get_source_type_display()
            block = f"--- Source: {title} ---\n{text}"

            if total_len + len(block) > knowledge_limit:
                remaining = knowledge_limit - total_len
                if remaining > 300:
                    knowledge_blocks.append(block[:remaining])
                break

            knowledge_blocks.append(block)
            total_len += len(block)

        if knowledge_blocks:
            parts.extend([
                "",
                "=== BASE DOCUMENTAIRE ===",
                "\n\n".join(knowledge_blocks),
            ])

    parts.extend([
        "",
        "=== COMPORTEMENT CONVERSATIONNEL ===",
        "Commence naturellement l'appel.",
        "Pose une seule question à la fois.",
        "Reformule si nécessaire.",
        "À la fin, résume brièvement ce qui a été demandé ou décidé.",
    ])

    return "\n".join(part for part in parts if part is not None)