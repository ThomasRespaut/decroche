# twilio_bridge/views.py
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.shortcuts import get_object_or_404
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

from .models import OutboundCall
from .services import launch_outbound_call


# -----------------------
# Health
# -----------------------

def health(request):
    return HttpResponse("ok", status=200)


# -----------------------
# Inbound voice
# -----------------------

@csrf_exempt
def voice(request):
    caller = request.POST.get("From") or request.GET.get("From", "")
    call_sid = request.POST.get("CallSid") or request.GET.get("CallSid", "")
    custom_prompt = request.GET.get("prompt", "").strip()

    vr = VoiceResponse()
    connect = Connect()

    stream = Stream(
        url=f"{settings.PUBLIC_WSS_BASE_URL}/twilio-stream",
        name="openai-realtime-bridge",
    )

    stream.parameter(name="caller", value=caller)
    stream.parameter(name="callSidCustom", value=call_sid)
    stream.parameter(name="direction", value="inbound")
    stream.parameter(name="custom_prompt", value=custom_prompt)

    connect.append(stream)
    vr.append(connect)
    vr.hangup()

    return HttpResponse(str(vr), content_type="text/xml")


# -----------------------
# Outbound TwiML
# -----------------------

@csrf_exempt
def outbound_bridge_twiml(request):
    to_number = request.GET.get("to", "")
    prospect_name = request.GET.get("name", "")
    company = request.GET.get("company", "")
    custom_prompt = request.GET.get("prompt", "")

    vr = VoiceResponse()
    connect = Connect()

    stream = Stream(
        url=f"{settings.PUBLIC_WSS_BASE_URL}/twilio-stream",
        name="openai-realtime-bridge-outbound",
    )

    stream.parameter(name="target_number", value=to_number)
    stream.parameter(name="prospect_name", value=prospect_name)
    stream.parameter(name="company", value=company)
    stream.parameter(name="direction", value="outbound")
    stream.parameter(name="custom_prompt", value=custom_prompt)

    connect.append(stream)
    vr.append(connect)
    vr.hangup()

    return HttpResponse(str(vr), content_type="text/xml")


# -----------------------
# Launch outbound call
# -----------------------

@csrf_exempt
def call_bridge(request):
    to_number = request.GET.get("to", "").strip()
    prospect_name = request.GET.get("name", "").strip()
    company = request.GET.get("company", "").strip()
    custom_prompt = request.GET.get("prompt", "").strip()

    if not to_number:
        return JsonResponse({"ok": False, "error": "Paramètre 'to' manquant"}, status=400)

    call_obj = OutboundCall.objects.create(
        to_number=to_number,
        prospect_name=prospect_name,
        company=company,
        custom_prompt=custom_prompt,
        status="initiated",
    )

    try:
        call = launch_outbound_call(
            to_number,
            prospect_name,
            company,
            custom_prompt,
        )

        call_obj.call_sid = call.sid
        call_obj.save(update_fields=["call_sid"])

        return JsonResponse({
            "ok": True,
            "call_sid": call.sid,
            "db_id": call_obj.id,
        })

    except Exception as e:
        call_obj.status = "failed"
        call_obj.save(update_fields=["status"])

        return JsonResponse({"ok": False, "error": str(e)}, status=500)


# -----------------------
# Status callback
# -----------------------

@csrf_exempt
def status(request):
    call_sid = request.POST.get("CallSid")
    call_status = request.POST.get("CallStatus", "unknown")
    duration = request.POST.get("CallDuration")

    if not call_sid:
        return HttpResponse(status=200)

    try:
        call_obj = OutboundCall.objects.get(call_sid=call_sid)
        call_obj.status = call_status

        if duration:
            call_obj.duration = int(duration)

        call_obj.save()
    except OutboundCall.DoesNotExist:
        pass

    return HttpResponse(status=200)