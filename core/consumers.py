# -*- coding: utf-8 -*-
import asyncio
import base64
import json

import websockets
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings


TWILIO_FRAME_MS = 20


def b64_to_bytes(data: str) -> bytes:
    return base64.b64decode(data)


def bytes_to_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class TwilioStreamConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print("=== WS CONNECT appelé ===")
        print("scope.type =", self.scope.get("type"))
        print("scope.path =", self.scope.get("path"))
        print("headers =", self.scope.get("headers"))

        await self.accept()
        print("=== WS ACCEPT OK ===")

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

        self.echo_test_frames_left = 0

    async def disconnect(self, close_code):
        print(f"=== WS DISCONNECT code={close_code} ===")

        try:
            if self.sender_task and not self.sender_task.done():
                self.sender_task.cancel()
        except Exception as e:
            print("disconnect sender_task error:", repr(e))

        try:
            if self.openai_task and not self.openai_task.done():
                self.openai_task.cancel()
        except Exception as e:
            print("disconnect openai_task error:", repr(e))

        try:
            if self.openai_ws:
                await self.openai_ws.close()
        except Exception as e:
            print("disconnect openai_ws error:", repr(e))

        try:
            await self.out_q.put(None)
        except Exception:
            pass

    async def send_to_twilio_loop(self):
        print("=== send_to_twilio_loop démarré ===")
        try:
            while True:
                frame_b64 = await self.out_q.get()
                if frame_b64 is None:
                    print("=== send_to_twilio_loop stop ===")
                    return

                if not self.stream_sid:
                    continue

                print("<<< ENVOI AUDIO VERS TWILIO")
                await self.send(text_data=json.dumps({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": frame_b64},
                }))

                await asyncio.sleep(TWILIO_FRAME_MS / 1000.0)

        except asyncio.CancelledError:
            print("send_to_twilio_loop cancelled")
        except Exception as e:
            print("send_to_twilio_loop error:", repr(e))

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            print("=== WS RECEIVE appelé ===")
            print("text_data =", text_data[:700])

        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except Exception as e:
            print("JSON decode error:", repr(e))
            return

        event = data.get("event")
        print("Twilio event =", event)

        if event == "connected":
            print("Twilio connected event")
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

            print("=== START EVENT ===")
            print("stream_sid =", self.stream_sid)
            print("call_sid =", self.call_sid)
            print("call_context =", self.call_context)

            self.echo_test_frames_left = 25
            print("=== ECHO TEST ARME ===")
            print("echo_test_frames_left =", self.echo_test_frames_left)

            self.sender_task = asyncio.create_task(self.send_to_twilio_loop())

            try:
                await self.connect_openai_and_bootstrap()
            except Exception as e:
                print("Erreur bootstrap OpenAI:", repr(e))
                await self.close()

            return

        if event == "media":
            payload = data.get("media", {}).get("payload")
            print("media event reçu, payload présent =", bool(payload))
            print("echo_test_frames_left avant test =", self.echo_test_frames_left)

            if not payload:
                return

            # Test Twilio -> Twilio
            if self.echo_test_frames_left > 0:
                self.echo_test_frames_left -= 1
                print(">>> ECHO TEST frame envoyée à Twilio, restantes =", self.echo_test_frames_left)
                await self.out_q.put(payload)

            # Audio entrant vers OpenAI
            if self.openai_ws:
                try:
                    await self.openai_ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": payload,
                    }))
                except Exception as e:
                    print("Erreur envoi audio vers OpenAI:", repr(e))
            return

        if event == "stop":
            print("=== STOP EVENT ===")
            try:
                await self.out_q.put(None)
            except Exception as e:
                print("out_q stop error:", repr(e))

            try:
                if self.openai_ws:
                    await self.openai_ws.close()
            except Exception as e:
                print("openai close error:", repr(e))
            return

        print("Event non géré =", event)

    async def recv_openai_event(self, timeout=5):
        raw = await asyncio.wait_for(self.openai_ws.recv(), timeout=timeout)
        evt = json.loads(raw)
        print("OpenAI event reçu sync =", evt.get("type"))
        return evt

    async def connect_openai_and_bootstrap(self):
        print("=== connect_openai_and_bootstrap appelé ===")
        url = f"wss://api.openai.com/v1/realtime?model={settings.OPENAI_REALTIME_MODEL}"
        print("OpenAI URL =", url)

        self.openai_ws = await websockets.connect(
            url,
            additional_headers=[
                ("Authorization", f"Bearer {settings.OPENAI_API_KEY}"),
                ("OpenAI-Beta", "realtime=v1"),
            ],
            ping_interval=20,
            ping_timeout=20,
            max_size=2**22,
        )
        print("=== OpenAI websocket connecté ===")

        # 1) Premier événement attendu à l'ouverture
        first_evt = await self.recv_openai_event(timeout=5)
        print("FIRST OPENAI EVENT =", first_evt)

        # 2) Mise à jour session avec schéma audio officiel
        prompt = self.call_context.get("custom_prompt") or (
            "Tu es l'agent téléphonique IA de démonstration de Décroche.ai. "
            "Tu parles uniquement en français. "
            "Tu es naturel, fluide, professionnel et concis."
        )

        session_update = {
            "type": "session.update",
            "session": {
                "instructions": prompt,
                "modalities": ["audio"],
                "audio": {
                    "input": {
                        "format": "g711_ulaw",
                        "transcription": {
                            "model": "gpt-4o-transcribe",
                            "language": "fr",
                        },
                        "turn_detection": {
                            "type": "server_vad",
                            "create_response": False,
                        },
                    },
                    "output": {
                        "format": "g711_ulaw",
                        "voice": settings.OPENAI_VOICE,
                    },
                },
            },
        }

        print("Envoi session.update")
        await self.openai_ws.send(json.dumps(session_update))
        print("session.update envoyé OK")

        session_updated_evt = await self.recv_openai_event(timeout=5)
        print("SESSION UPDATED EVENT =", session_updated_evt)

        # 3) Message utilisateur explicite
        item_evt = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Lance l'appel maintenant. "
                            "Dis bonjour en français, présente-toi brièvement comme Décroche.ai, "
                            "puis pose une question courte."
                        ),
                    }
                ],
            },
        }

        print("Envoi conversation.item.create")
        await self.openai_ws.send(json.dumps(item_evt))
        print("conversation.item.create envoyé OK")

        item_created_evt = await self.recv_openai_event(timeout=5)
        print("ITEM CREATED EVENT =", item_created_evt)

        # 4) Demande de réponse audio
        print("Envoi response.create")
        await self.openai_ws.send(json.dumps({
            "type": "response.create",
            "response": {
                "modalities": ["audio"],
            },
        }))
        print("response.create envoyé OK")

        # Ensuite seulement on bascule en écoute continue
        self.openai_task = asyncio.create_task(self.openai_to_twilio_loop())

    async def openai_to_twilio_loop(self):
        print("=== openai_to_twilio_loop démarré ===")
        buffer = b""

        try:
            while True:
                raw = await self.openai_ws.recv()
                evt = json.loads(raw)
                event_type = evt.get("type")
                print("OpenAI event =", event_type)

                if event_type == "response.created":
                    print("RESPONSE CREATED:", evt)
                    continue

                if event_type == "response.output_audio.delta":
                    print("AUDIO DELTA RECU")
                    delta = evt.get("delta")
                    if not delta:
                        continue

                    # Pour g711_ulaw, on peut renvoyer directement le delta base64 à Twilio
                    print(">>> CHUNK OPENAI MIS EN FILE POUR TWILIO")
                    await self.out_q.put(delta)
                    continue

                if event_type == "response.output_audio.done":
                    print("AUDIO DONE:", evt)
                    continue

                if event_type == "response.output_text.done":
                    print("AI:", evt.get("text"))
                    continue

                if event_type == "conversation.item.input_audio_transcription.completed":
                    print("USER:", evt.get("transcript"))
                    continue

                if event_type == "error":
                    print("OPENAI ERROR:", evt)
                    continue

                if event_type == "response.done":
                    print("RESPONSE DONE:", evt)
                    continue

                print("OpenAI event non géré =", evt)

        except asyncio.CancelledError:
            print("openai_to_twilio_loop cancelled")
        except Exception as e:
            print("openai_to_twilio_loop error:", repr(e))
            try:
                await self.close()
            except Exception as e2:
                print("close error:", repr(e2))