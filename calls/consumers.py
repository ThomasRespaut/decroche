# calls/consumers.py
import asyncio
import base64
import json
import os
from urllib.parse import parse_qs

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
        self.stream_sid = None
        self.call_sid = None
        self.call_session = None
        self.agent = None
        self.business_profile = None
        self.openai_ws = None
        self.openai_receiver_task = None
        self.call_started_at = timezone.now()

        query_string = self.scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        self.call_sid = (params.get("call_sid") or [None])[0]

        await self.accept()

        if not self.call_sid:
            await self.close()
            return

        self.call_session = await self.get_call_session(self.call_sid)
        if not self.call_session:
            await self.close()
            return

        self.agent = await self.get_agent(self.call_session.agent_id)
        if not self.agent:
            await self.close()
            return

        self.business_profile = await self.get_business_profile(self.agent.user_id)

        try:
            await self.connect_openai()
            await self.init_openai_session()
            self.openai_receiver_task = asyncio.create_task(
                self.forward_openai_to_twilio()
            )
        except Exception:
            await self.close()

    async def disconnect(self, close_code):
        if self.openai_receiver_task:
            self.openai_receiver_task.cancel()

        if self.openai_ws:
            try:
                await self.openai_ws.close()
            except Exception:
                pass

        if self.call_session:
            await self.mark_call_ended(self.call_session.id)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except Exception:
            return

        event_type = data.get("event")

        if event_type == "start":
            start_data = data.get("start", {})
            self.stream_sid = start_data.get("streamSid") or self.stream_sid

            if self.call_session:
                await self.update_stream_sid(self.call_session.id, self.stream_sid)

        elif event_type == "media":
            media = data.get("media", {})
            payload = media.get("payload")

            if payload and self.openai_ws:
                await self.send_audio_to_openai(payload)

        elif event_type == "stop":
            await self.close()

    async def connect_openai(self):
        api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY manquante")

        url = f"wss://api.openai.com/v1/realtime?model={REALTIME_MODEL}"

        self.openai_ws = await websockets.connect(
            url,
            additional_headers={
                "Authorization": f"Bearer {api_key}",
                "OpenAI-Beta": "realtime=v1",
            },
            max_size=None,
        )

    async def init_openai_session(self):
        instructions = await self.build_instructions()

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

        greeting_text = self.agent.greeting_message.strip() if self.agent.greeting_message else ""
        if greeting_text:
            await self.openai_ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "input_text",
                            "text": greeting_text,
                        }
                    ],
                },
            }))

            await self.openai_ws.send(json.dumps({
                "type": "response.create",
            }))

    async def send_audio_to_openai(self, base64_ulaw_payload):
        if not self.openai_ws:
            return

        await self.openai_ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": base64_ulaw_payload,
        }))

    async def forward_openai_to_twilio(self):
        try:
            async for message in self.openai_ws:
                data = json.loads(message)
                event_type = data.get("type")

                if event_type == "response.audio.delta":
                    audio_delta = data.get("delta")
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
                        await self.append_transcript(self.call_session.id, transcript_delta)

                elif event_type == "conversation.item.input_audio_transcription.completed":
                    transcript_text = data.get("transcript", "").strip()
                    if transcript_text and self.call_session:
                        await self.create_call_message(
                            call_session_id=self.call_session.id,
                            role="user",
                            content=transcript_text,
                        )

                elif event_type == "response.done":
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
                        if full_text and self.call_session:
                            await self.create_call_message(
                                call_session_id=self.call_session.id,
                                role="assistant",
                                content=full_text,
                            )
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

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