from django.db import models
from accounts.models import User


class AgentSettings(models.Model):
    TONE_CHOICES = [
        ("professionnel", "Professionnel"),
        ("chaleureux", "Chaleureux"),
        ("dynamique", "Dynamique"),
        ("premium", "Premium"),
        ("rassurant", "Rassurant"),
        ("direct", "Direct"),
    ]

    VOICE_CHOICES = [
        ("alloy", "Alloy"),
        ("ash", "Ash"),
        ("ballad", "Ballad"),
        ("coral", "Coral"),
        ("echo", "Echo"),
        ("fable", "Fable"),
        ("nova", "Nova"),
        ("onyx", "Onyx"),
        ("sage", "Sage"),
        ("shimmer", "Shimmer"),
        ("verse", "Verse"),
        ("marin", "Marin"),
        ("cedar", "Cedar"),
    ]

    LANGUAGE_CHOICES = [
        ("fr", "Français"),
        ("en", "Anglais"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="agent_settings",
    )

    ai_name = models.CharField(max_length=100, default="Assistant IA")

    greeting_message = models.TextField(
        default="Bonjour, je suis l'assistant IA, comment puis-je vous aider ?"
    )

    system_prompt = models.TextField(blank=True)

    tone = models.CharField(
        max_length=50,
        choices=TONE_CHOICES,
        default="professionnel",
    )

    voice = models.CharField(
        max_length=50,
        choices=VOICE_CHOICES,
        default="alloy",
    )

    language = models.CharField(
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default="fr",
    )

    twilio_phone_number = models.CharField(max_length=30, blank=True)

    # Comportement général
    interruptible = models.BooleanField(
        default=True,
        help_text="Autorise l'appelant à interrompre l'agent pendant qu'il parle.",
    )
    max_call_duration_seconds = models.PositiveIntegerField(
        default=600,
        help_text="Durée maximale d'un appel en secondes.",
    )
    response_style = models.CharField(
        max_length=100,
        blank=True,
        default="Réponses courtes, naturelles et claires.",
        help_text="Style global de réponse de l'agent.",
    )

    # Fonctionnalités
    enable_sms_summary = models.BooleanField(default=True)
    enable_transcription = models.BooleanField(default=True)
    enable_call_recording = models.BooleanField(default=False)

    # Outils / actions
    enable_rag = models.BooleanField(
        default=True,
        help_text="Permet à l'agent d'utiliser la base documentaire.",
    )
    enable_appointment_booking = models.BooleanField(
        default=False,
        help_text="Permet à l'agent de proposer ou prendre des rendez-vous.",
    )
    enable_table_booking = models.BooleanField(
        default=False,
        help_text="Permet à l'agent de gérer des réservations.",
    )
    enable_human_transfer = models.BooleanField(
        default=False,
        help_text="Permet de transférer vers un humain ou de proposer un rappel.",
    )
    enable_sms_followup = models.BooleanField(
        default=False,
        help_text="Permet l'envoi de SMS de suivi après interaction.",
    )

    fallback_message = models.TextField(
        blank=True,
        default="Je n'ai pas cette information pour le moment, mais je peux prendre un message.",
        help_text="Réponse de secours si l'agent ne sait pas répondre.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Agent IA - {self.user.email}"


class BusinessProfile(models.Model):
    ACTIVITY_CHOICES = [
        ("restaurant", "Restaurant"),
        ("medical", "Cabinet médical"),
        ("beauty", "Beauté / Bien-être"),
        ("real_estate", "Immobilier"),
        ("lawyer", "Cabinet juridique"),
        ("plumber", "Plomberie"),
        ("electrician", "Électricité"),
        ("retail", "Commerce"),
        ("agency", "Agence"),
        ("other", "Autre"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="business_profile",
    )

    company_name = models.CharField(max_length=255)
    activity_type = models.CharField(
        max_length=50,
        choices=ACTIVITY_CHOICES,
        default="other",
    )
    phone = models.CharField(max_length=30, blank=True)
    website_url = models.URLField(blank=True)

    business_description = models.TextField(blank=True)
    opening_hours = models.TextField(blank=True)

    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)

    extra_notes = models.TextField(
        blank=True,
        help_text="Informations internes utiles à l'agent.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.company_name or self.user.email


class AgentTool(models.Model):
    TOOL_CHOICES = [
        ("take_message", "Prendre un message"),
        ("book_appointment", "Prendre un rendez-vous"),
        ("book_table", "Réserver une table"),
        ("send_sms", "Envoyer un SMS"),
        ("transfer_human", "Transférer vers un humain"),
        ("faq_search", "Rechercher dans la base documentaire"),
    ]

    agent = models.ForeignKey(
        AgentSettings,
        on_delete=models.CASCADE,
        related_name="tools",
    )
    tool_key = models.CharField(max_length=50, choices=TOOL_CHOICES)
    enabled = models.BooleanField(default=True)

    config_json = models.JSONField(
        blank=True,
        null=True,
        help_text="Configuration spécifique de l'outil.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("agent", "tool_key")

    def __str__(self):
        return f"{self.agent.user.email} - {self.tool_key}"


class KnowledgeSource(models.Model):
    SOURCE_TYPE_CHOICES = [
        ("website", "Site web"),
        ("pdf", "PDF"),
        ("text", "Texte libre"),
        ("faq", "FAQ"),
    ]

    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("processing", "En cours"),
        ("ready", "Prêt"),
        ("error", "Erreur"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="knowledge_sources",
    )

    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES)
    title = models.CharField(max_length=255, blank=True)

    website_url = models.URLField(blank=True)
    file = models.FileField(
        upload_to="knowledge_pdfs/",
        blank=True,
        null=True,
    )

    raw_text = models.TextField(
        blank=True,
        help_text="Texte brut fourni directement par l'utilisateur.",
    )
    extracted_text = models.TextField(
        blank=True,
        help_text="Texte extrait automatiquement depuis un site ou un PDF.",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    error_message = models.TextField(blank=True)

    last_synced_at = models.DateTimeField(blank=True, null=True)
    page_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)

    use_ocr = models.BooleanField(
        default=False,
        help_text="Indique si une OCR doit être tentée pour ce document.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title or f"{self.get_source_type_display()} - {self.user.email}"


class KnowledgeChunk(models.Model):
    source = models.ForeignKey(
        KnowledgeSource,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()

    metadata_json = models.JSONField(
        blank=True,
        null=True,
        help_text="Métadonnées utiles : page, section, url, titre...",
    )

    embedding = models.JSONField(
        blank=True,
        null=True,
        help_text="Embedding stocké en JSON pour une V1 simple.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("source", "chunk_index")
        ordering = ["source", "chunk_index"]

    def __str__(self):
        return f"Chunk {self.chunk_index} - {self.source_id}"


class FrequentlyAskedQuestion(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="faqs",
    )
    question = models.CharField(max_length=255)
    answer = models.TextField()
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.question


class AgentFeedback(models.Model):
    CHANNEL_CHOICES = [
        ("text", "Texte"),
        ("voice", "Voix"),
        ("scenario", "Scénario"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="agent_feedbacks",
    )

    question = models.TextField()
    agent_answer = models.TextField()
    expected_answer = models.TextField()
    comment = models.TextField(blank=True)

    channel = models.CharField(
        max_length=20,
        choices=CHANNEL_CHOICES,
        default="text",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Feedback #{self.pk} - {self.user} - {self.channel}"