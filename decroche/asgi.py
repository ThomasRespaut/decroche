# -*- coding: utf-8 -*-
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "decroche.settings")

django_asgi_app = get_asgi_application()

import calls.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(calls.routing.websocket_urlpatterns)
    ),
})