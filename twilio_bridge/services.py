# twilio_bridge/services.py

from urllib.parse import urlencode
from django.conf import settings
from twilio.rest import Client


def get_twilio_client():
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise Exception("Twilio credentials missing")
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def launch_outbound_call(to_number, prospect_name="", company="", custom_prompt=""):
    client = get_twilio_client()

    if not settings.TWILIO_TEST_CALLER_NUMBER:
        raise Exception("TWILIO_TEST_CALLER_NUMBER missing in settings")

    params = {"to": to_number}

    if prospect_name:
        params["name"] = prospect_name

    if company:
        params["company"] = company

    if custom_prompt:
        params["prompt"] = custom_prompt

    twiml_url = (
        f"{settings.PUBLIC_BASE_URL}/twilio-bridge/outbound-bridge-twiml?"
        f"{urlencode(params)}"
    )

    status_callback_url = f"{settings.PUBLIC_BASE_URL}/twilio-bridge/status"

    call = client.calls.create(
        to=to_number,
        from_=settings.TWILIO_TEST_CALLER_NUMBER,
        url=twiml_url,
        method="GET",
        status_callback=status_callback_url,
        status_callback_method="POST",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )

    return call