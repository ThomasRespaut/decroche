# -*- coding: utf-8 -*-
import asyncio
import base64
import json

import websockets
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings


TWILIO_FRAME_BYTES = 160  # 20 ms en G.711 u-law / 8 kHz / mono
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
        self.openai_task = None

        self.call_context = {
            "direction": "outbound",
            "custom_prompt": "",
            "prospect_name": "",
            "target_number": "",
        }

        print("✅ WebSocket Twilio connecté")

    async def disconnect(self, close_code):
        print(f"❌ WebSocket fermé (code={close_code})")

        try:
            if self.sender_task and not self.sender_task.done():
                self.sender_task.cancel()
        except Exception:
            pass

        try:
            if self.openai_task and not self.openai_task.done():
                self.openai_task.cancel()
        except Exception:
            pass

        try:
            if self.openai_ws:
                await self.openai_ws.close()
        except Exception:
            pass

        try:
            await self.out_q.put(None)
        except Exception:
            pass

    async def send_to_twilio_loop(self):
        try:
            while True:
                frame_b64 = await self.out_q.get()
                if frame_b64 is None:
                    return

                if not self.stream_sid:
                    continue

                await self.send(text_data=json.dumps({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": frame_b64},
                }))

                await asyncio.sleep(TWILIO_FRAME_MS / 1000.0)

        except asyncio.CancelledError:
            return
        except Exception as e:
            print("❌ Erreur send_to_twilio_loop:", repr(e))

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            print("❌ JSON Twilio invalide")
            return

        event = data.get("event")

        if event == "connected":
            print("🔌 Twilio stream connected")
            return

        if event == "start":
            start_data = data.get("start", {}) or {}
            params = start_data.get("customParameters", {}) or {}

            self.stream_sid = start_data.get("streamSid")
            self.call_sid = start_data.get("callSid")

            self.call_context["custom_prompt"] = params.get("custom_prompt", "")
            self.call_context["prospect_name"] = params.get("prospect_name", "")
            self.call_context["target_number"] = params.get("target_number", "")
            self.call_context["direction"] = params.get("direction", "outbound")

            print("📞 CALL START")
            print("   stream_sid =", self.stream_sid)
            print("   call_sid   =", self.call_sid)
            print("   context    =", self.call_context)

            self.sender_task = asyncio.create_task(self.send_to_twilio_loop())

            await self.connect_openai()
            return

        if event == "media":
            payload = data.get("media", {}).get("payload")

            if not payload:
                return

            if not self.openai_ws:
                print("⚠️ Audio reçu avant connexion OpenAI")
                return

            try:
                await self.openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": payload,
                }))
            except Exception as e:
                print("❌ Erreur envoi audio vers OpenAI:", repr(e))
            return

        if event == "stop":
            print("📴 CALL END")

            try:
                await self.out_q.put(None)
            except Exception:
                pass

            try:
                if self.openai_ws:
                    await self.openai_ws.close()
            except Exception:
                pass

            return

        print("ℹ️ Event Twilio non géré:", event)

    async def connect_openai(self):
        url = f"wss://api.openai.com/v1/realtime?model={settings.OPENAI_REALTIME_MODEL}"

        try:
            self.openai_ws = await websockets.connect(
                url,
                additional_headers=[
                    ("Authorization", f"Bearer {settings.OPENAI_API_KEY}"),
                ],
                ping_interval=20,
                ping_timeout=20,
                max_size=2**22,
            )
        except Exception as e:
            print("❌ Impossible de connecter OpenAI Realtime:", repr(e))
            await self.close()
            return

        print("🤖 OpenAI connecté")

        await self.init_openai_session()

        self.openai_task = asyncio.create_task(self.openai_to_twilio_loop())

    async def init_openai_session(self):
        prompt = self.call_context.get("custom_prompt") or (
            "Tu es l'agent téléphonique IA de démonstration de Décroche.ai. "
            "Tu parles uniquement en français. "
            "Tu es naturel, fluide, professionnel, chaleureux et très concis. "
            "Tu fais une démonstration crédible d'appel téléphonique pour entreprise. "
            "Tu peux expliquer que Décroche.ai répond aux appels, prend des messages, "
            "qualifie les demandes et automatise certaines prises de rendez-vous "
            "ou réservations. "
            "Tu poses une seule question à la fois."
        )

        session_update = {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": settings.OPENAI_REALTIME_MODEL,
                "instructions": prompt,
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "audio": {
                    "input": {
                        "turn_detection": {"type": "server_vad"},
                        "transcription": {
                            "model": "gpt-4o-transcribe",
                            "language": "fr",
                        },
                    },
                    "output": {
                        "voice": settings.OPENAI_VOICE,
                    },
                },
            },
        }

        await self.openai_ws.send(json.dumps(session_update))
        print("📤 session.update envoyé à OpenAI")

        await self.openai_ws.send(json.dumps({
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": (
                    "Commence immédiatement l'appel en français. "
                    "Dis bonjour, présente-toi brièvement comme la démonstration de Décroche.ai, "
                    "puis continue naturellement avec une phrase courte."
                ),
            },
        }))
        print("📤 response.create envoyé à OpenAI")

    async def openai_to_twilio_loop(self):
        buffer = b""

        try:
            while True:
                raw = await self.openai_ws.recv()
                evt = json.loads(raw)
                event_type = evt.get("type")

                if event_type == "session.updated":
                    print("✅ SESSION UPDATED")
                    continue

                if event_type == "error":
                    print("❌ OPENAI ERROR:", evt)
                    continue

                if event_type == "response.created":
                    print("🟢 RESPONSE CREATED")
                    continue

                if event_type == "response.output_audio.delta":
                    delta = evt.get("delta")
                    if not delta:
                        continue

                    buffer += b64_to_bytes(delta)

                    while len(buffer) >= TWILIO_FRAME_BYTES:
                        chunk = buffer[:TWILIO_FRAME_BYTES]
                        buffer = buffer[TWILIO_FRAME_BYTES:]
                        await self.out_q.put(bytes_to_b64(chunk))

                    continue

                if event_type == "response.output_audio.done":
                    print("🔊 Audio IA terminé")
                    continue

                if event_type == "conversation.item.input_audio_transcription.completed":
                    transcript = (evt.get("transcript") or "").strip()
                    if transcript:
                        print("👤 USER:", transcript)
                    continue

                if event_type == "response.output_text.done":
                    text = (evt.get("text") or "").strip()
                    if text:
                        print("🤖 AI:", text)
                    continue

                if event_type == "response.done":
                    print("✅ RESPONSE DONE")
                    continue

        except asyncio.CancelledError:
            return
        except websockets.exceptions.ConnectionClosed as e:
            print("❌ OpenAI websocket fermé:", repr(e))
        except Exception as e:
            print("❌ ERREUR BRIDGE:", repr(e))
        finally:
            try:
                await self.close()
            except Exception:
                pass