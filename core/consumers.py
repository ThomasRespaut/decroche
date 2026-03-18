# -*- coding: utf-8 -*-
import asyncio
import base64
import json

import websockets
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings


TWILIO_FRAME_BYTES = 160  # 20ms audio (PCMU 8kHz)
TWILIO_FRAME_MS = 20


def b64_to_bytes(data: str) -> bytes:
    return base64.b64decode(data)


def bytes_to_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class TwilioStreamConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

        self.stream_sid = None
        self.call_sid = None
        self.openai_ws = None

        self.out_q = asyncio.Queue(maxsize=2000)
        self.sender_task = None

        self.call_context = {
            "direction": "outbound",
            "custom_prompt": "",
            "prospect_name": "",
            "target_number": "",
        }

        print("✅ WebSocket Twilio connecté")

    async def disconnect(self, close_code):
        print("❌ WebSocket fermé")

        try:
            if self.sender_task:
                self.sender_task.cancel()
        except:
            pass

        try:
            if self.openai_ws:
                await self.openai_ws.close()
        except:
            pass

    # --------------------------------------------------
    # Envoi audio vers Twilio
    # --------------------------------------------------
    async def send_to_twilio_loop(self):
        while True:
            frame_b64 = await self.out_q.get()
            if frame_b64 is None:
                return

            if not self.stream_sid:
                continue

            await self.send(text_data=json.dumps({
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": frame_b64}
            }))

            await asyncio.sleep(TWILIO_FRAME_MS / 1000)

    # --------------------------------------------------
    # Réception messages Twilio
    # --------------------------------------------------
    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        data = json.loads(text_data)
        event = data.get("event")

        # Connexion OK
        if event == "connected":
            return

        # START CALL
        if event == "start":
            start_data = data.get("start", {})
            params = start_data.get("customParameters", {})

            self.stream_sid = start_data.get("streamSid")
            self.call_sid = start_data.get("callSid")

            self.call_context["custom_prompt"] = params.get("custom_prompt", "")
            self.call_context["prospect_name"] = params.get("prospect_name", "")
            self.call_context["target_number"] = params.get("target_number", "")
            self.call_context["direction"] = params.get("direction", "outbound")

            print("📞 CALL START", self.call_context)

            # Lance envoi audio Twilio
            self.sender_task = asyncio.create_task(self.send_to_twilio_loop())

            # Connect OpenAI
            await self.connect_openai()

            return

        # AUDIO entrant
        if event == "media":
            payload = data.get("media", {}).get("payload")

            if payload and self.openai_ws:
                await self.openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": payload
                }))
            return

        # FIN appel
        if event == "stop":
            print("📴 CALL END")

            try:
                await self.out_q.put(None)
            except:
                pass

            try:
                if self.openai_ws:
                    await self.openai_ws.close()
            except:
                pass

    # --------------------------------------------------
    # Connexion OpenAI Realtime
    # --------------------------------------------------
    async def connect_openai(self):
        url = f"wss://api.openai.com/v1/realtime?model={settings.OPENAI_REALTIME_MODEL}"

        self.openai_ws = await websockets.connect(
            url,
            additional_headers=[
                ("Authorization", f"Bearer {settings.OPENAI_API_KEY}")
            ],
            ping_interval=20,
            ping_timeout=20,
        )

        print("🤖 OpenAI connecté")

        await self.init_openai_session()

        asyncio.create_task(self.openai_to_twilio_loop())

    # --------------------------------------------------
    # Initialisation IA
    # --------------------------------------------------
    async def init_openai_session(self):
        prompt = self.call_context.get("custom_prompt") or (
            "Tu es un agent téléphonique IA français. "
            "Tu es naturel, fluide, professionnel et très concis. "
            "Tu fais une démonstration de Décroche.ai. "
            "Tu poses une seule question à la fois."
        )

        await self.openai_ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": settings.OPENAI_REALTIME_MODEL,
                "instructions": prompt,
                "audio": {
                    "input": {
                        "turn_detection": {"type": "server_vad"}
                    },
                    "output": {
                        "voice": settings.OPENAI_VOICE
                    }
                }
            }
        }))

        # Première phrase
        await self.openai_ws.send(json.dumps({
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": "Commence la conversation maintenant."
            }
        }))

    # --------------------------------------------------
    # OpenAI → Twilio
    # --------------------------------------------------
    async def openai_to_twilio_loop(self):
        buffer = b""

        try:
            while True:
                raw = await self.openai_ws.recv()
                evt = json.loads(raw)
                t = evt.get("type")

                # Audio IA
                if t == "response.output_audio.delta":
                    delta = evt.get("delta")

                    if delta:
                        buffer += b64_to_bytes(delta)

                        while len(buffer) >= TWILIO_FRAME_BYTES:
                            chunk = buffer[:TWILIO_FRAME_BYTES]
                            buffer = buffer[TWILIO_FRAME_BYTES:]

                            await self.out_q.put(bytes_to_b64(chunk))

                # Texte utilisateur
                elif t == "conversation.item.input_audio_transcription.completed":
                    print("👤 USER:", evt.get("transcript"))

                # Texte IA
                elif t == "response.output_text.done":
                    print("🤖 AI:", evt.get("text"))

        except Exception as e:
            print("❌ ERREUR BRIDGE:", e)
            await self.close()