# twilio_bridge/urls.py
from django.urls import path
from . import views

app_name = "twilio_bridge"

urlpatterns = [
    path("health", views.health, name="health"),
    path("voice", views.voice, name="voice"),
    path("outbound-bridge-twiml", views.outbound_bridge_twiml, name="outbound_bridge_twiml"),
    path("call-bridge", views.call_bridge, name="call_bridge"),
    path("status", views.status, name="status"),
]