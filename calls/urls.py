from django.urls import path
from .views import twilio_incoming_call, twilio_call_status_callback

urlpatterns = [
    path("twilio/incoming/", twilio_incoming_call, name="twilio_incoming_call"),
    path("twilio/status/", twilio_call_status_callback, name="twilio_call_status_callback"),

    # alias temporaires
    path("voice", twilio_incoming_call),
    path("status", twilio_call_status_callback),
]