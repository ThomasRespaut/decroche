from django import forms

from accounts.models import Profile
from agents.models import AgentSettings, AgentTool, KnowledgeSource


INPUT_CLASS = "form-control"
TEXTAREA_CLASS = "form-control"
SELECT_CLASS = "form-control"
CHECKBOX_CLASS = "form-checkbox"


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "company_name",
            "activity_type",
            "phone",
            "business_description",
            "opening_hours",
            "website_url",
            "address",
            "city",
            "postal_code",
            "extra_notes",
        ]
        widgets = {
            "company_name": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "Ex. Décroche.ai",
            }),
            "activity_type": forms.Select(attrs={
                "class": SELECT_CLASS,
            }),
            "phone": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "Ex. 01 23 45 67 89",
            }),
            "business_description": forms.Textarea(attrs={
                "class": TEXTAREA_CLASS,
                "rows": 5,
                "placeholder": "Décris l’activité, les services proposés, les demandes fréquentes...",
            }),
            "opening_hours": forms.Textarea(attrs={
                "class": TEXTAREA_CLASS,
                "rows": 4,
                "placeholder": "Ex. Lun-Ven 9h-18h, Sam 10h-14h, fermé le dimanche",
            }),
            "website_url": forms.URLInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "https://www.monentreprise.fr",
            }),
            "address": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "Adresse",
            }),
            "city": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "Ville",
            }),
            "postal_code": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "Code postal",
            }),
            "extra_notes": forms.Textarea(attrs={
                "class": TEXTAREA_CLASS,
                "rows": 5,
                "placeholder": "Consignes internes, cas particuliers, infos importantes à connaître...",
            }),
        }


class AgentAIForm(forms.ModelForm):
    class Meta:
        model = AgentSettings
        fields = [
            "ai_name",
            "tone",
            "voice",
            "language",
            "greeting_message",
            "system_prompt",
            "response_style",
            "fallback_message",
            "twilio_phone_number",
            "interruptible",
            "max_call_duration_seconds",
        ]
        widgets = {
            "ai_name": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "Ex. Clara",
            }),
            "tone": forms.Select(attrs={
                "class": SELECT_CLASS,
            }),
            "voice": forms.Select(attrs={
                "class": SELECT_CLASS,
            }),
            "language": forms.Select(attrs={
                "class": SELECT_CLASS,
            }),
            "greeting_message": forms.Textarea(attrs={
                "class": TEXTAREA_CLASS,
                "rows": 4,
                "placeholder": "Bonjour, vous êtes bien chez ...",
            }),
            "system_prompt": forms.Textarea(attrs={
                "class": TEXTAREA_CLASS,
                "rows": 8,
                "placeholder": "Consignes détaillées pour l’agent : quoi dire, quoi demander, quoi éviter...",
            }),
            "response_style": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "Ex. Réponses courtes, naturelles et rassurantes",
            }),
            "fallback_message": forms.Textarea(attrs={
                "class": TEXTAREA_CLASS,
                "rows": 3,
                "placeholder": "Message utilisé si l’agent ne trouve pas l’information",
            }),
            "twilio_phone_number": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "Ex. +33123456789",
            }),
            "max_call_duration_seconds": forms.NumberInput(attrs={
                "class": INPUT_CLASS,
                "min": 30,
                "step": 30,
                "placeholder": "600",
            }),
            "interruptible": forms.CheckboxInput(attrs={
                "class": CHECKBOX_CLASS,
            }),
        }


class AgentOptionsForm(forms.ModelForm):
    class Meta:
        model = AgentSettings
        fields = [
            "enable_sms_summary",
            "enable_transcription",
            "enable_call_recording",
            "enable_rag",
            "enable_appointment_booking",
            "enable_table_booking",
            "enable_human_transfer",
            "enable_sms_followup",
        ]
        widgets = {
            "enable_sms_summary": forms.CheckboxInput(attrs={
                "class": CHECKBOX_CLASS,
            }),
            "enable_transcription": forms.CheckboxInput(attrs={
                "class": CHECKBOX_CLASS,
            }),
            "enable_call_recording": forms.CheckboxInput(attrs={
                "class": CHECKBOX_CLASS,
            }),
            "enable_rag": forms.CheckboxInput(attrs={
                "class": CHECKBOX_CLASS,
            }),
            "enable_appointment_booking": forms.CheckboxInput(attrs={
                "class": CHECKBOX_CLASS,
            }),
            "enable_table_booking": forms.CheckboxInput(attrs={
                "class": CHECKBOX_CLASS,
            }),
            "enable_human_transfer": forms.CheckboxInput(attrs={
                "class": CHECKBOX_CLASS,
            }),
            "enable_sms_followup": forms.CheckboxInput(attrs={
                "class": CHECKBOX_CLASS,
            }),
        }


class AgentToolForm(forms.ModelForm):
    class Meta:
        model = AgentTool
        fields = [
            "tool_key",
            "enabled",
            "config_json",
        ]
        widgets = {
            "tool_key": forms.Select(attrs={
                "class": SELECT_CLASS,
            }),
            "enabled": forms.CheckboxInput(attrs={
                "class": CHECKBOX_CLASS,
            }),
            "config_json": forms.Textarea(attrs={
                "class": TEXTAREA_CLASS,
                "rows": 4,
                "placeholder": '{"calendar_id": "primary"}',
            }),
        }


class KnowledgeSourceForm(forms.ModelForm):
    class Meta:
        model = KnowledgeSource
        fields = [
            "source_type",
            "title",
            "website_url",
            "file",
            "raw_text",
            "use_ocr",
        ]
        widgets = {
            "source_type": forms.Select(attrs={
                "class": SELECT_CLASS,
            }),
            "title": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "Ex. Menu restaurant / FAQ / Site principal",
            }),
            "website_url": forms.URLInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "https://www.monentreprise.fr",
            }),
            "file": forms.ClearableFileInput(attrs={
                "class": INPUT_CLASS,
                "accept": ".pdf",
            }),
            "raw_text": forms.Textarea(attrs={
                "class": TEXTAREA_CLASS,
                "rows": 6,
                "placeholder": "Texte libre à ajouter à la base de connaissance...",
            }),
            "use_ocr": forms.CheckboxInput(attrs={
                "class": CHECKBOX_CLASS,
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        source_type = cleaned_data.get("source_type")
        website_url = cleaned_data.get("website_url")
        file = cleaned_data.get("file")
        raw_text = cleaned_data.get("raw_text")

        if source_type == "website" and not website_url:
            self.add_error(
                "website_url",
                "Veuillez renseigner une URL pour une source de type site web.",
            )

        if source_type == "pdf" and not file:
            self.add_error(
                "file",
                "Veuillez importer un PDF pour une source de type PDF.",
            )

        if source_type in ["text", "faq"] and not raw_text:
            self.add_error(
                "raw_text",
                "Veuillez renseigner du texte pour cette source.",
            )

        return cleaned_data


# Compatibilité temporaire si ton code importe encore AgentSettingsForm
class AgentSettingsForm(AgentAIForm):
    pass

from django import forms
from agents.models import AgentFeedback


class AgentTestMessageForm(forms.Form):
    message = forms.CharField(
        label="",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Pose une question à ton agent...",
                "class": "test-textarea",
            }
        ),
    )


class AgentFeedbackForm(forms.ModelForm):
    class Meta:
        model = AgentFeedback
        fields = ["question", "agent_answer", "expected_answer", "comment", "channel"]
        widgets = {
            "question": forms.Textarea(attrs={
                "rows": 3,
                "class": "test-textarea",
                "placeholder": "Question utilisateur"
            }),
            "agent_answer": forms.Textarea(attrs={
                "rows": 4,
                "class": "test-textarea",
                "placeholder": "Réponse initiale de l'agent"
            }),
            "expected_answer": forms.Textarea(attrs={
                "rows": 4,
                "class": "test-textarea",
                "placeholder": "Réponse idéale attendue"
            }),
            "comment": forms.Textarea(attrs={
                "rows": 3,
                "class": "test-textarea",
                "placeholder": "Pourquoi corriger cette réponse ?"
            }),
            "channel": forms.Select(attrs={
                "class": "test-select",
            }),
        }