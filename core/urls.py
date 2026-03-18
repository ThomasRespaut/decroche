from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("demo/live/", views.live_demo, name="live_demo"),
    path("demo/request-call/", views.request_demo_call, name="request_demo_call"),
    path("api/realtime/session/", views.create_realtime_session, name="create_realtime_session"),

    # Twilio / bridge
    path("outbound-bridge-twiml", views.outbound_bridge_twiml, name="outbound_bridge_twiml"),
    path("twilio-status", views.twilio_status, name="twilio_status"),
]