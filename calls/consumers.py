# calls/consumers.py
import asyncio
import json
import os

import websockets
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.utils import timezone

from agents.models import AgentSettings, CallMessage, CallSession
from agents.services.prompt_builder import build_agent_system_prompt


REALTIME_MODEL = getattr(settings, "OPENAI_REALTIME_MODEL", "gpt-realtime")


class TwilioStreamConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print("=== WS CONNECT CALLED ===")
        print("scope type =", self.scope.get("type"))
        print("path =", self.scope.get("path"))
        print("query_string raw =", self.scope.get("query_string"))

        self.stream_sid = None
        self.call_sid = None
        self.call_session = None
        self.agent = None
        self.business_profile = None
        self.openai_ws = None
        self.openai_receiver_task = None
        self.call_started_at = timezone.now()
        self.openai_ready = False

        await self.accept()
        print("=== WS ACCEPTED ===")

    async def disconnect(self, close_code):
        print("=== WS DISCONNECT ===", close_code)

        if self.openai_receiver_task:
            self.openai_receiver_task.cancel()

        if self.openai_ws:
            try:
                await self.openai_ws.close()
            except Exception as exc:
                print("=== ERROR CLOSING OPENAI WS ===", repr(exc))

        if self.call_session:
            await self.mark_call_ended(self.call_session.id)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            print("=== WS RECEIVE WITH NO TEXT_DATA ===")
            return

        try:
            data = json.loads(text_data)
        except Exception as exc:
            print("=== ERROR PARSING WS JSON ===", repr(exc))
            print("raw text_data =", text_data[:500])
            return

        event_type = data.get("event")
        print("=== WS EVENT ===", event_type)

        if event_type == "start":
            start_data = data.get("start", {})
            self.stream_sid = start_data.get("streamSid") or self.stream_sid
            self.call_sid = start_data.get("callSid") or self.call_sid

            print("start_data =", start_data)
            print("stream_sid =", self.stream_sid)
            print("call_sid =", self.call_sid)

            if not self.call_sid:
                print("=== NO CALL SID IN START EVENT, CLOSING ===")
                await self.close()
                return

            self.call_session = await self.get_call_session(self.call_sid)
            print("call_session =", self.call_session)

            if not self.call_session:
                print("=== CALL SESSION NOT FOUND, CLOSING ===")
                await self.close()
                return

            await self.update_stream_sid(self.call_session.id, self.stream_sid)

            self.agent = await self.get_agent(self.call_session.agent_id)
            print("agent =", self.agent)

            if not self.agent:
                print("=== AGENT NOT FOUND, CLOSING ===")
                await self.close()
                return

            self.business_profile = await self.get_business_profile(self.agent.user_id)
            print("business_profile =", self.business_profile)

            try:
                await self.connect_openai()
                await self.init_openai_session()
                self.openai_receiver_task = asyncio.create_task(
                    self.forward_openai_to_twilio()
                )
                self.openai_ready = True
                print("=== OPENAI RECEIVER TASK STARTED ===")
            except Exception as exc:
                print("=== ERROR DURING OPENAI CONNECT/INIT ===", repr(exc))
                await self.close()

        elif event_type == "media":
            media = data.get("media", {})
            payload = media.get("payload")
            print("media received, payload exists =", bool(payload), "openai_ready =", self.openai_ready)

            if payload and self.openai_ws and self.openai_ready:
                await self.send_audio_to_openai(payload)

        elif event_type == "stop":
            print("=== WS STOP RECEIVED ===")
            await self.close()

        else:
            print("=== UNHANDLED WS EVENT ===", event_type)

    async def connect_openai(self):
        api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY manquante")

        url = f"wss://api.openai.com/v1/realtime?model={REALTIME_MODEL}"
        print("=== CONNECTING TO OPENAI ===", url)

        self.openai_ws = await websockets.connect(
            url,
            additional_headers={
                "Authorization": f"Bearer {api_key}",
                "OpenAI-Beta": "realtime=v1",
            },
            max_size=None,
        )

        print("=== OPENAI CONNECTED ===")
        print("voice =", self.agent.voice)
        print("model =", REALTIME_MODEL)

    # 1) dans init_openai_session(), remplace le greeting par une simple response.create guidée
    async def init_openai_session(self):
        instructions = await self.build_instructions()
        print("=== BUILD INSTRUCTIONS DONE ===")
        print("instructions preview =", instructions[:500])

        session_payload = {
            "type": "session.update",
            "session": {
                "instructions": instructions,
                "voice": self.agent.voice,
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "modalities": ["audio", "text"],
                "turn_detection": {
                    "type": "server_vad",
                },
            },
        }

        await self.openai_ws.send(json.dumps(session_payload))
        print("=== SESSION.UPDATE SENT ===")

        greeting_text = (self.agent.greeting_message or "").strip()
        print("greeting_text =", greeting_text)

        if greeting_text:
            await self.openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                    "instructions": greeting_text,
                },
            }))
            print("=== GREETING response.create SENT ===")

    async def send_audio_to_openai(self, base64_ulaw_payload):
        if not self.openai_ws:
            print("=== OPENAI WS MISSING, AUDIO NOT SENT ===")
            return

        await self.openai_ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": base64_ulaw_payload,
        }))

    # 2) dans forward_openai_to_twilio(), loggue TOUS les événements OpenAI au début
    async def forward_openai_to_twilio(self):
        print("=== FORWARD OPENAI TO TWILIO LOOP STARTED ===")
        try:
            async for message in self.openai_ws:
                data = json.loads(message)
                event_type = data.get("type")
                print("=== OPENAI EVENT ===", event_type)
                print("OPENAI DATA PREVIEW =", json.dumps(data)[:1000])

                if event_type == "response.audio.delta":
                    audio_delta = data.get("delta")
                    print("audio delta exists =", bool(audio_delta), "stream_sid =", self.stream_sid)

                    if audio_delta and self.stream_sid:
                        await self.send(text_data=json.dumps({
                            "event": "media",
                            "streamSid": self.stream_sid,
                            "media": {
                                "payload": audio_delta
                            },
                        }))

                elif event_type == "response.audio_transcript.delta":
                    transcript_delta = data.get("delta", "")
                    if transcript_delta and self.call_session:
                        print("assistant transcript delta =", transcript_delta[:200])
                        await self.append_transcript(self.call_session.id, transcript_delta)

                elif event_type == "conversation.item.input_audio_transcription.completed":
                    transcript_text = data.get("transcript", "").strip()
                    print("user transcript =", transcript_text)

                    if transcript_text and self.call_session:
                        await self.create_call_message(
                            call_session_id=self.call_session.id,
                            role="user",
                            content=transcript_text,
                        )

                elif event_type == "response.done":
                    print("=== OPENAI RESPONSE DONE ===")
                    output = data.get("response", {}).get("output", [])
                    for item in output:
                        if item.get("type") != "message":
                            continue

                        text_parts = []
                        for content in item.get("content", []):
                            if content.get("type") in {"audio_transcript", "text", "output_text"}:
                                text_value = content.get("text") or content.get("transcript") or ""
                                if text_value:
                                    text_parts.append(text_value)

                        full_text = " ".join(text_parts).strip()
                        print("assistant full_text =", full_text)

                        if full_text and self.call_session:
                            await self.create_call_message(
                                call_session_id=self.call_session.id,
                                role="assistant",
                                content=full_text,
                            )
        except asyncio.CancelledError:
            print("=== OPENAI LOOP CANCELLED ===")
        except Exception as exc:
            print("=== ERROR IN OPENAI LOOP ===", repr(exc))

    async def build_instructions(self):
        return await sync_to_async(build_agent_system_prompt)(
            self.agent,
            self.business_profile,
        )

    @sync_to_async
    def get_call_session(self, call_sid):
        return (
            CallSession.objects
            .select_related("agent", "user")
            .filter(call_sid=call_sid)
            .first()
        )

    @sync_to_async
    def get_agent(self, agent_id):
        if not agent_id:
            return None
        return (
            AgentSettings.objects
            .select_related("user")
            .filter(id=agent_id)
            .first()
        )

    @sync_to_async
    def get_business_profile(self, user_id):
        agent = (
            AgentSettings.objects
            .select_related("user__business_profile")
            .filter(user_id=user_id)
            .first()
        )
        if not agent:
            return None
        return getattr(agent.user, "business_profile", None)

    @sync_to_async
    def update_stream_sid(self, call_session_id, stream_sid):
        CallSession.objects.filter(id=call_session_id).update(
            stream_sid=stream_sid,
            updated_at=timezone.now(),
        )

    @sync_to_async
    def append_transcript(self, call_session_id, text_delta):
        session = CallSession.objects.filter(id=call_session_id).first()
        if not session:
            return

        current = session.transcript or ""
        session.transcript = current + text_delta
        session.save(update_fields=["transcript", "updated_at"])

    @sync_to_async
    def create_call_message(self, call_session_id, role, content):
        return CallMessage.objects.create(
            call_session_id=call_session_id,
            role=role,
            content=content,
        )

    @sync_to_async
    def mark_call_ended(self, call_session_id):
        session = CallSession.objects.filter(id=call_session_id).first()
        if not session:
            return

        if not session.ended_at:
            session.ended_at = timezone.now()

        if session.started_at:
            session.duration_seconds = max(
                0,
                int((session.ended_at - session.started_at).total_seconds())
            )

        if session.status == "in_progress":
            session.status = "completed"

        session.save(update_fields=[
            "ended_at",
            "duration_seconds",
            "status",
            "updated_at",
        ])