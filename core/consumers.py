# -*- coding: utf-8 -*-
import asyncio
import base64
import json

import websockets
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings


TWILIO_FRAME_MS = 20
TWILIO_FRAME_BYTES = 160  # 20 ms en G711 µ-law 8kHz mono


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

        self.closed = False
        self.initial_greeting_done = False
        self.vad_enabled = False
        self.forward_audio_to_openai = False

        # petit test Twilio -> Twilio au début
        self.echo_test_frames_left = 12

    async def disconnect(self, close_code):
        print(f"=== WS DISCONNECT code={close_code} ===")
        self.closed = True

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

    async def safe_close(self):
        if self.closed:
            return
        self.closed = True
        try:
            await self.close()
        except Exception as e:
            print("safe_close error:", repr(e))

    async def send_to_twilio_loop(self):
        print("=== send_to_twilio_loop démarré ===")
        try:
            while True:
                frame_b64 = await self.out_q.get()

                if frame_b64 is None:
                    print("=== send_to_twilio_loop stop ===")
                    return

                if not self.stream_sid:
                    print("send_to_twilio_loop: stream_sid absent, frame ignorée")
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

            self.sender_task = asyncio.create_task(self.send_to_twilio_loop())

            try:
                await self.connect_openai_and_bootstrap()
            except Exception as e:
                print("Erreur bootstrap OpenAI:", repr(e))
                await self.safe_close()

            return

        if event == "media":
            payload = data.get("media", {}).get("payload")
            print("media event reçu, payload présent =", bool(payload))

            if not payload:
                return

            # test immédiat Twilio -> Twilio
            if self.echo_test_frames_left > 0:
                self.echo_test_frames_left -= 1
                print(">>> ECHO TEST frame envoyée à Twilio, restantes =", self.echo_test_frames_left)
                await self.out_q.put(payload)

            # tant que le greeting n'est pas fini, on n'envoie pas l'audio vers OpenAI
            if not self.forward_audio_to_openai:
                print("audio Twilio ignoré temporairement pendant greeting initial")
                return

            if self.openai_ws:
                try:
                    await self.openai_ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": payload,
                    }))
                except Exception as e:
                    print("Erreur envoi audio vers OpenAI:", repr(e))
            else:
                print("media reçu mais openai_ws non initialisé")

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

    async def wait_for_openai_event(self, accepted_types, timeout=8):
        while True:
            evt = await self.recv_openai_event(timeout=timeout)
            evt_type = evt.get("type")

            if evt_type in accepted_types:
                return evt

            if evt_type == "error":
                raise RuntimeError(f"Erreur OpenAI reçue: {evt}")

            print("Event sync ignoré pendant attente =", evt_type)

    async def enable_vad_after_greeting(self):
        if self.vad_enabled:
            return

        print("=== ACTIVATION DU VAD APRES GREETING ===")
        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                    "create_response": True,
                    "interrupt_response": True,
                }
            },
        }

        await self.openai_ws.send(json.dumps(session_update))
        self.vad_enabled = True
        self.forward_audio_to_openai = True

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

        first_evt = await self.recv_openai_event(timeout=5)
        print("FIRST OPENAI EVENT =", first_evt)

        prompt = self.call_context.get("custom_prompt") or (
            "Tu es l'assistant téléphonique IA de démonstration de Décroche.ai. "
            "Tu parles uniquement en français. "
            "Tu es chaleureux, naturel, professionnel et très concis. "
            "Tu poses une seule question à la fois."
        )

        session_update = {
            "type": "session.update",
            "session": {
                "instructions": prompt,
                "voice": settings.OPENAI_VOICE,
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "input_audio_transcription": {
                    "model": "gpt-4o-transcribe",
                    "language": "fr",
                },
                "turn_detection": None,
            },
        }

        print("Envoi session.update")
        await self.openai_ws.send(json.dumps(session_update))
        print("session.update envoyé OK")

        session_updated_evt = await self.wait_for_openai_event(
            accepted_types={"session.updated"},
            timeout=8,
        )
        print("SESSION UPDATED EVENT =", session_updated_evt)

        self.openai_task = asyncio.create_task(self.openai_to_twilio_loop())
        await asyncio.sleep(0)

        # on crée explicitement un item utilisateur
        item_evt = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Commence immédiatement l'appel. "
                            "Dis bonjour, présente-toi brièvement comme Décroche.ai, "
                            "explique que c'est une démonstration, "
                            "puis pose une question courte."
                        ),
                    }
                ],
            },
        }

        print("Envoi conversation.item.create")
        await self.openai_ws.send(json.dumps(item_evt))
        print("conversation.item.create envoyé OK")

        first_response = {
            "type": "response.create",
            "response": {
                "modalities": ["audio"],
            },
        }

        print("Envoi response.create (greeting initial)")
        await self.openai_ws.send(json.dumps(first_response))
        print("response.create envoyé OK")

    async def openai_to_twilio_loop(self):
        print("=== openai_to_twilio_loop démarré ===")
        audio_buffer = b""
        text_buffer = ""

        try:
            while True:
                raw = await self.openai_ws.recv()
                evt = json.loads(raw)
                event_type = evt.get("type")
                print("OpenAI event =", event_type)

                if event_type == "session.updated":
                    print("SESSION UPDATED OK:", evt)
                    continue

                if event_type == "conversation.item.created":
                    print("CONVERSATION ITEM CREATED:", evt)
                    continue

                if event_type == "response.created":
                    print("RESPONSE CREATED:", evt)
                    text_buffer = ""
                    continue

                if event_type == "response.output_item.added":
                    print("OUTPUT ITEM ADDED:", evt)
                    continue

                if event_type == "response.output_text.delta":
                    delta = evt.get("delta") or ""
                    if delta:
                        text_buffer += delta
                        print("AI TEXT DELTA:", delta)
                    continue

                if event_type == "response.output_text.done":
                    final_text = evt.get("text") or text_buffer
                    print("AI:", final_text)
                    text_buffer = ""
                    continue

                if event_type == "response.output_audio.delta":
                    delta_b64 = evt.get("delta")
                    if not delta_b64:
                        continue

                    print("AUDIO DELTA RECU")
                    audio_buffer += b64_to_bytes(delta_b64)

                    while len(audio_buffer) >= TWILIO_FRAME_BYTES:
                        frame = audio_buffer[:TWILIO_FRAME_BYTES]
                        audio_buffer = audio_buffer[TWILIO_FRAME_BYTES:]
                        print(">>> FRAME OPENAI MISE EN FILE POUR TWILIO")
                        await self.out_q.put(bytes_to_b64(frame))

                    continue

                if event_type == "response.output_audio.done":
                    print("AUDIO DONE:", evt)

                    if audio_buffer:
                        print("Flush reliquat audio vers Twilio:", len(audio_buffer), "octets")
                        await self.out_q.put(bytes_to_b64(audio_buffer))
                        audio_buffer = b""

                    continue

                if event_type == "response.done":
                    print("RESPONSE DONE:", evt)

                    if not self.initial_greeting_done:
                        self.initial_greeting_done = True
                        await self.enable_vad_after_greeting()

                    continue

                if event_type == "conversation.item.input_audio_transcription.completed":
                    print("USER:", evt.get("transcript"))
                    continue

                if event_type == "input_audio_buffer.speech_started":
                    print("USER SPEECH STARTED")
                    continue

                if event_type == "input_audio_buffer.speech_stopped":
                    print("USER SPEECH STOPPED")
                    continue

                if event_type == "error":
                    print("OPENAI ERROR:", evt)
                    continue

                print("OpenAI event non géré =", evt)

        except asyncio.CancelledError:
            print("openai_to_twilio_loop cancelled")
        except Exception as e:
            print("openai_to_twilio_loop error:", repr(e))
            await self.safe_close()
