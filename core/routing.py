from django.urls import re_path
from .consumers import TwilioStreamConsumer

websocket_urlpatterns = [
    re_path(r"^twilio-stream/?$", TwilioStreamConsumer.as_asgi()),
]