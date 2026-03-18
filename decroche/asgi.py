# -*- coding: utf-8 -*-
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "decroche.settings")

print("=== CHARGEMENT ASGI ===")

django_asgi_app = get_asgi_application()

import core.routing
print("=== core.routing importé ===")
print("=== websocket_urlpatterns =", core.routing.websocket_urlpatterns, "===")

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        URLRouter(core.routing.websocket_urlpatterns)
    ),
})