# calls/views.py
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from agents.models import AgentSettings, CallSession


@csrf_exempt
def twilio_incoming_call(request):
    """
    Webhook HTTP appelé par Twilio lors d'un appel entrant.
    Twilio envoie les infos du call en POST.
    """
    called_number = (request.POST.get("To") or "").strip()
    from_number = (request.POST.get("From") or "").strip()
    call_sid = (request.POST.get("CallSid") or "").strip()

    agent = (
        AgentSettings.objects
        .select_related("user", "user__business_profile")
        .filter(twilio_phone_number=called_number)
        .first()
    )

    if not agent:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-FR">Ce numéro n'est pas configuré.</Say>
    <Hangup/>
</Response>"""
        return HttpResponse(xml, content_type="text/xml")

    CallSession.objects.get_or_create(
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
            },
        },
    )

    public_wss_base_url = getattr(settings, "PUBLIC_WSS_BASE_URL", "").rstrip("/")
    if not public_wss_base_url:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-FR">Le service n'est pas disponible pour le moment.</Say>
    <Hangup/>
</Response>"""
        return HttpResponse(xml, content_type="text/xml")

    stream_url = (
        f"{public_wss_base_url}/ws/twilio-stream/"
        f"?call_sid={escape(call_sid)}"
    )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{escape(stream_url)}" />
    </Connect>
</Response>"""

    return HttpResponse(xml, content_type="text/xml")


# calls/views.py
from django.views.decorators.http import require_POST


@csrf_exempt
@require_POST
def twilio_call_status_callback(request):
    call_sid = (request.POST.get("CallSid") or "").strip()
    call_status = (request.POST.get("CallStatus") or "").strip()

    session = CallSession.objects.filter(call_sid=call_sid).first()
    if session:
        session.status = call_status if call_status in {
            "initiated", "ringing", "in_progress", "completed",
            "busy", "failed", "no_answer", "canceled"
        } else session.status

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

    return HttpResponse("OK")