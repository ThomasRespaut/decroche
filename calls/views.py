# -*- coding: utf-8 -*-
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from agents.models import AgentSettings, CallSession


def normalize_phone(value: str) -> str:
    """
    Normalise un numéro Twilio reçu en POST.
    """
    value = (value or "").strip()
    value = value.replace(" ", "")

    if value and not value.startswith("+") and value.isdigit():
        value = f"+{value}"

    return value


def xml_response(xml: str) -> HttpResponse:
    return HttpResponse(xml, content_type="text/xml")


@csrf_exempt
@require_POST
def twilio_incoming_call(request):
    """
    Webhook HTTP appelé par Twilio lors d'un appel entrant.
    """
    called_number = normalize_phone(request.POST.get("To"))
    from_number = normalize_phone(request.POST.get("From"))
    call_sid = (request.POST.get("CallSid") or "").strip()

    print(
        "=== TWILIO INCOMING CALL ===",
        f"call_sid={call_sid}",
        f"to={called_number}",
        f"from={from_number}",
    )

    agent = (
        AgentSettings.objects
        .select_related("user", "user__business_profile")
        .filter(twilio_phone_number=called_number)
        .first()
    )

    if not agent:
        print(
            "=== TWILIO AGENT NOT FOUND ===",
            f"call_sid={call_sid}",
            f"to={called_number}",
        )
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-FR">Ce numéro n'est pas configuré.</Say>
    <Hangup/>
</Response>"""
        return xml_response(xml)

    session, created = CallSession.objects.get_or_create(
        call_sid=call_sid,
        defaults={
            "user": agent.user,
            "agent": agent,
            "from_number": from_number,
            "to_number": called_number,
            "direction": "inbound",
            "status": "in_progress",
            "started_at": timezone.now(),
            "metadata_json": {
                "twilio_call_sid": call_sid,
                "called_number": called_number,
                "from_number": from_number,
            },
        },
    )

    if not created:
        updated = False

        if session.status != "in_progress":
            session.status = "in_progress"
            updated = True

        if not session.started_at:
            session.started_at = timezone.now()
            updated = True

        if not session.from_number and from_number:
            session.from_number = from_number
            updated = True

        if not session.to_number and called_number:
            session.to_number = called_number
            updated = True

        metadata = session.metadata_json or {}
        if metadata.get("called_number") != called_number or metadata.get("from_number") != from_number:
            metadata.update({
                "twilio_call_sid": call_sid,
                "called_number": called_number,
                "from_number": from_number,
            })
            session.metadata_json = metadata
            updated = True

        if updated:
            session.save(update_fields=[
                "status",
                "started_at",
                "from_number",
                "to_number",
                "metadata_json",
                "updated_at",
            ])

    print(
        "=== TWILIO CALL SESSION READY ===",
        f"call_sid={call_sid}",
        f"session_id={session.id}",
        f"agent_id={agent.id}",
        f"created={created}",
    )

    public_wss_base_url = getattr(settings, "PUBLIC_WSS_BASE_URL", "").rstrip("/")
    if not public_wss_base_url:
        print(
            "=== PUBLIC_WSS_BASE_URL MISSING ===",
            f"call_sid={call_sid}",
        )
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-FR">Le service n'est pas disponible pour le moment.</Say>
    <Hangup/>
</Response>"""
        return xml_response(xml)

    # Twilio <Stream url="..."> ne supporte pas les query strings.
    stream_url = f"{public_wss_base_url}/ws/twilio-stream/"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{escape(stream_url)}" />
    </Connect>
</Response>"""

    return xml_response(xml)


@csrf_exempt
@require_POST
def twilio_call_status_callback(request):
    call_sid = (request.POST.get("CallSid") or "").strip()
    call_status = (request.POST.get("CallStatus") or "").strip()

    allowed_statuses = {
        "initiated",
        "ringing",
        "in_progress",
        "completed",
        "busy",
        "failed",
        "no_answer",
        "canceled",
    }

    session = CallSession.objects.filter(call_sid=call_sid).first()
    if not session:
        print(
            "=== TWILIO STATUS SESSION NOT FOUND ===",
            f"call_sid={call_sid}",
            f"status={call_status}",
        )
        return HttpResponse("OK")

    if call_status in allowed_statuses:
        session.status = call_status

    if call_status in {"completed", "busy", "failed", "no_answer", "canceled"}:
        session.ended_at = timezone.now()
        if session.started_at:
            session.duration_seconds = max(
                0,
                int((session.ended_at - session.started_at).total_seconds())
            )

    session.save(update_fields=[
        "status",
        "ended_at",
        "duration_seconds",
        "updated_at",
    ])

    print(
        "=== TWILIO STATUS UPDATED ===",
        f"call_sid={call_sid}",
        f"status={session.status}",
        f"duration={session.duration_seconds}",
    )

    return HttpResponse("OK")


# Alias temporaires si Twilio pointe encore vers /voice et /status
voice = twilio_incoming_call
status = twilio_call_status_callback