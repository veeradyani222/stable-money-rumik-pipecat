from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from websockets.asyncio.client import connect as websockets_connect
from websockets.protocol import State

from app.core.config import get_settings
from app.domain.rumik_text import normalize_rumik_text

RUMIK_SAMPLE_RATE = 24000


@dataclass(frozen=True)
class _RumikTTSRequest:
    text: str
    context_id: str


class RumikTTSService:
    """HTTP bootstrap adapter for a persistent Pipecat Rumik TTS service."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def create_session(self, text: str) -> dict[str, Any]:
        if not self.settings.rumik_api_key:
            raise RuntimeError("RUMIK_API_KEY is required for Rumik TTS")
        rumik_text = normalize_rumik_text(text)[:2000]
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.settings.rumik_base_url}/v1/tts/ws-connect",
                headers={"Authorization": f"Bearer {self.settings.rumik_api_key}", "Content-Type": "application/json"},
                json={"text": rumik_text, "model": self.settings.rumik_tts_model},
            )
        data = response.json()
        if response.status_code >= 400:
            raise RuntimeError(f"Rumik session failed: {data}")
        return {**data, "text": rumik_text}


def create_pipecat_rumik_tts_service(adapter: RumikTTSService | None = None):
    from pipecat.frames.frames import (
        CancelFrame,
        EndFrame,
        ErrorFrame,
        Frame,
        StartFrame,
        TTSAudioRawFrame,
        TTSStoppedFrame,
    )
    from pipecat.services.settings import TTSSettings
    from pipecat.services.tts_service import WebsocketTTSService

    adapter = adapter or RumikTTSService()

    class PipecatRumikTTSService(WebsocketTTSService):
        def __init__(self):
            super().__init__(
                sample_rate=RUMIK_SAMPLE_RATE,
                push_start_frame=True,
                push_stop_frames=True,
                settings=TTSSettings(model=adapter.settings.rumik_tts_model, voice=None, language=None),
            )
            self._receive_task: asyncio.Task | None = None
            self._sender_task: asyncio.Task | None = None
            self._context_keepalive_task: asyncio.Task | None = None
            self._context_keepalive_interval_s = 1.0
            self._request_queue: asyncio.Queue[_RumikTTSRequest] = asyncio.Queue()
            self._active_request: _RumikTTSRequest | None = None
            self._active_done = asyncio.Event()
            self._pending_by_context: dict[str, int] = {}
            self._flushed_context_ids: set[str] = set()

        def can_generate_metrics(self) -> bool:
            return True

        async def preconnect(self) -> None:
            if self._websocket and self._websocket.state is State.OPEN:
                return
            await self._connect_websocket()

        async def start(self, frame: StartFrame):
            await super().start(frame)
            await self._connect()

        async def stop(self, frame: EndFrame):
            await super().stop(frame)
            await self._disconnect()

        async def cancel(self, frame: CancelFrame):
            await super().cancel(frame)
            await self._disconnect()

        async def _connect(self):
            await super()._connect()
            await self._connect_websocket()
            if self._websocket and not self._receive_task:
                self._receive_task = self.create_task(self._receive_task_handler(self._report_error))

        async def _disconnect(self):
            await super()._disconnect()
            if self._receive_task:
                await self.cancel_task(self._receive_task)
                self._receive_task = None
            await self._clear_request_state()
            await self._disconnect_websocket()

        async def _connect_websocket(self):
            try:
                if self._websocket and self._websocket.state is State.OPEN:
                    return
                session = await adapter.create_session("init")
                ws_url = session.get("ws_url")
                token = session.get("token")
                if not ws_url or not token:
                    raise RuntimeError(f"Rumik session response missing ws_url/token: {session}")
                self._websocket = await websockets_connect(f"{ws_url}?token={quote(str(token))}")
                await self._call_event_handler("on_connected")
                if self._active_request:
                    await self._send_active_request()
            except Exception as exc:
                self._websocket = None
                await self.push_error(error_msg=f"Rumik TTS connection failed: {exc}", exception=exc)
                await self._call_event_handler("on_connection_error", str(exc))

        async def _disconnect_websocket(self):
            try:
                await self.stop_all_metrics()
                if self._websocket:
                    try:
                        await self._websocket.send(json.dumps({"type": "close"}))
                    except Exception:
                        pass
                    finally:
                        await self._websocket.close()
            finally:
                self._websocket = None
                await self._call_event_handler("on_disconnected")

        def _get_websocket(self):
            if self._websocket:
                return self._websocket
            raise RuntimeError("Rumik WebSocket is not connected")

        async def _clear_request_state(self):
            if self._sender_task:
                await self.cancel_task(self._sender_task)
                self._sender_task = None
            if self._context_keepalive_task:
                await self.cancel_task(self._context_keepalive_task)
                self._context_keepalive_task = None
            self._request_queue = asyncio.Queue()
            self._active_request = None
            self._active_done = asyncio.Event()
            self._pending_by_context.clear()
            self._flushed_context_ids.clear()

        def _ensure_sender_task(self):
            if not self._sender_task:
                self._sender_task = self.create_task(self._sender_loop())

        def _ensure_context_keepalive_task(self):
            if not self._context_keepalive_task or self._context_keepalive_task.done():
                self._context_keepalive_task = self.create_task(self._context_keepalive_loop())

        async def _context_keepalive_loop(self):
            try:
                # Reconnect and synthesis can exceed Pipecat's idle-context timeout.
                while self._pending_by_context:
                    await asyncio.sleep(self._context_keepalive_interval_s)
                    for context_id in list(self._pending_by_context):
                        self._refresh_audio_context(context_id)
            except asyncio.CancelledError:
                raise
            finally:
                if self._context_keepalive_task is asyncio.current_task():
                    self._context_keepalive_task = None

        async def _send_active_request(self):
            if not self._active_request:
                return
            message = json.dumps({"text": self._active_request.text, "speaker_id": 0})
            await self._get_websocket().send(message)

        async def _send_or_reconnect_active_request(self):
            if not self._websocket or self._websocket.state is State.CLOSED:
                await self._connect()
                if not self._websocket:
                    raise RuntimeError("Rumik WebSocket reconnect failed")
                return
            try:
                await self._send_active_request()
            except Exception:
                if not await self._try_reconnect(report_error=self._report_error):
                    raise RuntimeError("Rumik WebSocket reconnect failed")

        async def _sender_loop(self):
            try:
                while True:
                    request = await self._request_queue.get()
                    self._active_request = request
                    self._active_done.clear()
                    try:
                        await self._send_or_reconnect_active_request()
                        await self._active_done.wait()
                    except Exception as exc:
                        await self.push_error(error_msg=f"Rumik TTS send failed: {exc}", exception=exc)
                        await self._complete_active_request()
                    finally:
                        self._active_request = None
                        self._request_queue.task_done()
            except asyncio.CancelledError:
                raise
            finally:
                self._sender_task = None

        async def _complete_active_request(self):
            request = self._active_request
            if not request:
                return
            pending = self._pending_by_context.get(request.context_id, 0) - 1
            if pending > 0:
                self._pending_by_context[request.context_id] = pending
            else:
                self._pending_by_context.pop(request.context_id, None)
            self._active_done.set()
            await self._finish_context_if_drained(request.context_id)

        async def _finish_context_if_drained(self, context_id: str):
            if context_id not in self._flushed_context_ids:
                return
            if self._pending_by_context.get(context_id, 0):
                return
            self._flushed_context_ids.discard(context_id)
            if self.audio_context_available(context_id):
                await self.append_to_audio_context(context_id, TTSStoppedFrame(context_id=context_id))
                await self.remove_audio_context(context_id)

        async def flush_audio(self, context_id: str | None = None):
            flush_id = context_id or self.get_active_audio_context_id()
            if not flush_id:
                return
            self._flushed_context_ids.add(flush_id)
            await self._finish_context_if_drained(flush_id)

        async def _handle_rumik_message(self, message: str | bytes):
            request = self._active_request
            if isinstance(message, bytes):
                if request:
                    await self.stop_ttfb_metrics()
                    await self.append_to_audio_context(
                        request.context_id,
                        TTSAudioRawFrame(message, RUMIK_SAMPLE_RATE, 1, context_id=request.context_id),
                    )
                return
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                return
            message_type = payload.get("type")
            if message_type == "done" and request:
                await self._complete_active_request()
            elif message_type == "queued":
                return
            elif payload.get("error"):
                await self.push_error(error_msg=f"Rumik TTS error: {payload}")
                await self._complete_active_request()

        async def _receive_messages(self):
            async for message in self._get_websocket():
                await self._handle_rumik_message(message)

        async def on_audio_context_interrupted(self, context_id: str):
            await self._disconnect()
            await super().on_audio_context_interrupted(context_id)

        async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
            try:
                if not self._websocket or self._websocket.state is State.CLOSED:
                    await self._connect()
                if not self._websocket:
                    raise RuntimeError("Rumik WebSocket is not connected")
                rumik_text = normalize_rumik_text(text)[:2000]
                request = _RumikTTSRequest(text=rumik_text, context_id=context_id)
                self._pending_by_context[context_id] = self._pending_by_context.get(context_id, 0) + 1
                await self._request_queue.put(request)
                self._ensure_sender_task()
                self._ensure_context_keepalive_task()
                await self.start_tts_usage_metrics(text)
                yield None
            except Exception as exc:
                yield ErrorFrame(error=f"Rumik TTS failed: {exc}")

    return PipecatRumikTTSService()
