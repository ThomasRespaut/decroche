# twilio_bridge/apps.py
from django.apps import AppConfig


class TwilioBridgeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "twilio_bridge"