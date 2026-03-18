# -*- coding: utf-8 -*-
import os
import re
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from twilio.rest import Client

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET, require_POST

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from xml.sax.saxutils import escape

load_dotenv()


def home(request):
    return render(request, "core/home.html")


@require_GET
def live_demo(request):
    return render(request, "core/live_demo.html")


@require_POST
def create_realtime_session(request):
    api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        return JsonResponse(
            {"error": "OPENAI_API_KEY manquante côté serveur."},
            status=500,
        )

    payload = {
        "session": {
            "type": "realtime",
            "model": "gpt-realtime",
            "instructions": (
                "Tu es l’agent vocal de démonstration de Décroche.ai. "
                "Tu réponds uniquement en français, de manière naturelle, concise, "
                "professionnelle et chaleureuse. "
                "Tu expliques que tu es une démonstration d’agent téléphonique IA pour entreprises. "
                "Tu peux simuler une prise de rendez-vous, une réservation, "
                "une qualification de besoin ou une prise de message. "
                "Tu poses une seule question à la fois et gardes des réponses courtes."
            ),
            "audio": {
                "input": {
                    "noise_reduction": {"type": "near_field"},
                    "transcription": {
                        "model": "gpt-4o-transcribe",
                        "language": "fr",
                    },
                    "turn_detection": {
                        "type": "server_vad",
                    },
                },
                "output": {
                    "voice": "marin",
                },
            },
        }
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/realtime/client_secrets",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
    except requests.RequestException as e:
        return JsonResponse(
            {
                "error": "Erreur réseau lors de la création de la session Realtime.",
                "details": repr(e),
            },
            status=502,
        )

    try:
        data = response.json()
    except ValueError:
        return JsonResponse(
            {
                "error": "Réponse invalide reçue depuis OpenAI.",
                "status_code": response.status_code,
                "raw_text": response.text[:2000],
            },
            status=500,
        )

    print("OPENAI REALTIME RAW RESPONSE =", data)

    if not response.ok:
        return JsonResponse(
            {
                "error": "Impossible de créer la session Realtime.",
                "status_code": response.status_code,
                "details": data,
            },
            status=response.status_code,
        )

    client_secret = data.get("value")
    expires_at = data.get("expires_at")
    session_obj = data.get("session")

    if not client_secret:
        return JsonResponse(
            {
                "error": "Session créée mais client_secret introuvable dans la réponse.",
                "details": data,
            },
            status=500,
        )

    return JsonResponse(
        {
            "ok": True,
            "client_secret": client_secret,
            "expires_at": expires_at,
            "session": session_obj,
        }
    )


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""

    phone = phone.strip()
    phone = phone.replace(" ", "").replace(".", "").replace("-", "")

    if re.fullmatch(r"0\d{9}", phone):
        return "+33" + phone[1:]

    if re.fullmatch(r"\+\d{8,15}", phone):
        return phone

    return ""


def build_demo_prompt(name: str = "") -> str:
    if name:
        return (
            f"Tu appelles {name} pour faire une démonstration vocale de Décroche.ai. "
            "Tu parles uniquement en français. "
            "Tu te présentes comme l'assistant téléphonique IA de démonstration de Décroche.ai. "
            "Tu expliques en quelques phrases que la solution permet de répondre aux appels, "
            "prendre des messages, qualifier les demandes et automatiser certaines réservations "
            "ou prises de rendez-vous. "
            "Tu restes chaleureux, naturel, professionnel et très concis. "
            "Tu poses une seule question à la fois. "
            "Si la personne répond peu, tu continues simplement la démonstration sans être insistant. "
            "L'objectif est de montrer une conversation fluide et crédible."
        )

    return (
        "Tu effectues un appel de démonstration pour Décroche.ai. "
        "Tu parles uniquement en français. "
        "Tu te présentes comme l'assistant téléphonique IA de démonstration de Décroche.ai. "
        "Tu expliques en quelques phrases que la solution permet de répondre aux appels, "
        "prendre des messages, qualifier les demandes et automatiser certaines réservations "
        "ou prises de rendez-vous. "
        "Tu restes chaleureux, naturel, professionnel et très concis. "
        "Tu poses une seule question à la fois. "
        "Si la personne répond peu, tu continues simplement la démonstration sans être insistant. "
        "L'objectif est de montrer une conversation fluide et crédible."
    )


@require_POST
def request_demo_call(request):
    raw_phone = request.POST.get("phone", "")
    prospect_name = (request.POST.get("name", "") or "").strip()

    phone = normalize_phone(raw_phone)
    if not phone:
        messages.error(request, "Numéro invalide.")
        return redirect("home")

    account_sid = os.getenv("TWILIO_ACCOUNT_SID") or getattr(settings, "TWILIO_ACCOUNT_SID", None)
    auth_token = os.getenv("TWILIO_AUTH_TOKEN") or getattr(settings, "TWILIO_AUTH_TOKEN", None)
    from_number = os.getenv("TWILIO_TEST_CALLER_NUMBER") or getattr(settings, "TWILIO_TEST_CALLER_NUMBER", None)
    public_base_url = os.getenv("PUBLIC_BASE_URL") or getattr(settings, "PUBLIC_BASE_URL", None)

    if not account_sid or not auth_token or not from_number or not public_base_url:
        messages.error(request, "Configuration Twilio / bridge incomplète côté serveur.")
        return redirect("home")

    custom_prompt = build_demo_prompt(prospect_name)

    params = {
        "to": phone,
        "prompt": custom_prompt,
    }
    if prospect_name:
        params["name"] = prospect_name

    twiml_url = f"{public_base_url}/outbound-bridge-twiml?{urlencode(params)}"

    try:
        client = Client(account_sid, auth_token)

        call = client.calls.create(
            to=phone,
            from_=from_number,
            url=twiml_url,
            method="GET",
            status_callback=f"{public_base_url}/twilio-status",
            status_callback_method="POST",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
        )

        print(f"APPEL IA LANCE vers {phone} | SID={call.sid} | TWIML_URL={twiml_url}")
        messages.success(request, "Votre appel de démonstration IA a bien été lancé.")
        return redirect("home")

    except Exception as e:
        print("Erreur Twilio request_demo_call:", repr(e))
        messages.error(request, "Impossible de lancer l'appel pour le moment.")
        return redirect("home")


@csrf_exempt
def outbound_bridge_twiml(request):
    """
    Twilio appelle cette route quand l'utilisateur décroche.
    On renvoie du XML (TwiML) qui connecte l'appel au websocket IA.
    """

    to_number = request.GET.get("to", "")
    prospect_name = request.GET.get("name", "")
    custom_prompt = request.GET.get("prompt", "")

    stream_url = f"{settings.PUBLIC_WSS_BASE_URL}/twilio-stream"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{escape(stream_url)}">
            <Parameter name="target_number" value="{escape(to_number)}" />
            <Parameter name="prospect_name" value="{escape(prospect_name)}" />
            <Parameter name="direction" value="outbound" />
            <Parameter name="custom_prompt" value="{escape(custom_prompt)}" />
        </Stream>
    </Connect>
</Response>"""

    return HttpResponse(twiml, content_type="application/xml")

@csrf_exempt
def twilio_status(request):
    """
    Callback Twilio pour suivre l'état des appels
    """

    call_sid = request.POST.get("CallSid")
    call_status = request.POST.get("CallStatus")
    to_number = request.POST.get("To")
    from_number = request.POST.get("From")

    print(
        f"[TWILIO STATUS] call_sid={call_sid} "
        f"status={call_status} to={to_number} from={from_number}"
    )

    return HttpResponse("ok")