from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from websockets.asyncio.client import connect as websockets_connect
from websockets.protocol import State

from app.core.config import get_settings
from app.core.http_client import get_shared_http_client
from app.domain.rumik_text import normalize_rumik_text

logger = logging.getLogger(__name__)

RUMIK_SAMPLE_RATE = 24000


def _log_rumik_event(event: str, **payload: Any) -> None:
    logger.info(
        "%s %s",
        event,
        json.dumps({"event": event, **payload}, ensure_ascii=False, default=str),
    )


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
        client = get_shared_http_client()
        started_at = time.monotonic()
        _log_rumik_event(
            "rumik_session_create_start",
            text_chars=len(rumik_text),
            model=self.settings.rumik_tts_model,
        )
        response = await client.post(
            f"{self.settings.rumik_base_url}/v1/tts/ws-connect",
            headers={"Authorization": f"Bearer {self.settings.rumik_api_key}", "Content-Type": "application/json"},
            json={"text": rumik_text, "model": self.settings.rumik_tts_model},
            timeout=20.0,
        )
        data = response.json()
        _log_rumik_event(
            "rumik_session_create_done",
            status_code=response.status_code,
            elapsed_s=round(time.monotonic() - started_at, 3),
            request_id=data.get("request_id"),
            expires_in=data.get("expires_in"),
            text_chars=len(rumik_text),
            model=self.settings.rumik_tts_model,
        )
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
    from pipecat.services.tts_service import TextAggregationMode, WebsocketTTSService

    adapter = adapter or RumikTTSService()

    class PipecatRumikTTSService(WebsocketTTSService):
        def __init__(self):
            super().__init__(
                sample_rate=RUMIK_SAMPLE_RATE,
                text_aggregation_mode=TextAggregationMode.SENTENCE,
                push_start_frame=True,
                push_stop_frames=True,
                settings=TTSSettings(model=adapter.settings.rumik_tts_model, voice=None, language=None),
            )
            self._receive_task: asyncio.Task | None = None
            self._sender_task: asyncio.Task | None = None
            self._context_keepalive_task: asyncio.Task | None = None
            self._websocket_keepalive_task: asyncio.Task | None = None
            self._context_keepalive_interval_s = 1.0
            self._websocket_keepalive_interval_s = 25.0
            self._websocket_keepalive_timeout_s = 5.0
            self._websocket_refresh_idle_s = 45.0
            self._websocket_refresh_connection_age_s = 90.0
            self._request_queue: asyncio.Queue[_RumikTTSRequest] = asyncio.Queue()
            self._active_request: _RumikTTSRequest | None = None
            self._active_done = asyncio.Event()
            self._pending_by_context: dict[str, int] = {}
            self._flushed_context_ids: set[str] = set()
            # Session pre-caching: fetch the next Rumik session token while
            # the current synthesis is still in progress so reconnections
            # only need a WebSocket handshake (~200ms) instead of
            # HTTP POST + WS handshake (~1.5s).
            self._cached_session: dict[str, Any] | None = None
            self._cached_session_time: float = 0.0
            self._session_prefetch_task: asyncio.Task | None = None
            self._interruption_reconnect_task: asyncio.Task | None = None
            self._SESSION_CACHE_TTL = 55.0  # seconds; discard stale tokens
            self._last_ws_connected_at: float | None = None
            self._last_ws_activity_at: float | None = None
            self._active_request_started_at: float | None = None
            self._active_audio_bytes = 0

        def can_generate_metrics(self) -> bool:
            return True

        def _websocket_state_name(self) -> str | None:
            state = getattr(self._websocket, "state", None)
            return getattr(state, "name", None)

        def _idle_age_s(self) -> float | None:
            if self._last_ws_activity_at is None:
                return None
            return round(time.monotonic() - self._last_ws_activity_at, 3)

        def _connection_age_s(self) -> float | None:
            if self._last_ws_connected_at is None:
                return None
            return round(time.monotonic() - self._last_ws_connected_at, 3)

        def _active_elapsed_s(self) -> float | None:
            if self._active_request_started_at is None:
                return None
            return round(time.monotonic() - self._active_request_started_at, 3)

        async def preconnect(self) -> None:
            if self._websocket and self._websocket.state is State.OPEN:
                _log_rumik_event(
                    "rumik_preconnect_skip_open",
                    ws_state=self._websocket_state_name(),
                    idle_age_s=self._idle_age_s(),
                    connection_age_s=self._connection_age_s(),
                )
                return
            _log_rumik_event("rumik_preconnect_start", ws_state=self._websocket_state_name())
            await self._connect_websocket(source="preconnect", prefetch=False)
            _log_rumik_event(
                "rumik_preconnect_done",
                ws_state=self._websocket_state_name(),
                idle_age_s=self._idle_age_s(),
                connection_age_s=self._connection_age_s(),
            )

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
            await self._connect_websocket(source="connect", prefetch=True)
            if self._websocket and not self._receive_task:
                self._receive_task = self.create_task(self._receive_task_handler(self._report_error))
            if self._websocket:
                self._ensure_websocket_keepalive_task()

        async def _disconnect(self):
            await super()._disconnect()
            if self._receive_task:
                await self.cancel_task(self._receive_task)
                self._receive_task = None
            await self._clear_request_state()
            await self._disconnect_websocket()

        async def _connect_websocket(self, *, source: str = "connect", prefetch: bool = True):
            started_at = time.monotonic()
            try:
                if self._websocket and self._websocket.state is State.OPEN:
                    _log_rumik_event(
                        "rumik_ws_connect_skip_open",
                        source=source,
                        ws_state=self._websocket_state_name(),
                        idle_age_s=self._idle_age_s(),
                        connection_age_s=self._connection_age_s(),
                    )
                    return
                _log_rumik_event(
                    "rumik_ws_connect_start",
                    source=source,
                    prefetch=prefetch,
                    ws_state=self._websocket_state_name(),
                    idle_age_s=self._idle_age_s(),
                    connection_age_s=self._connection_age_s(),
                    has_cached_session=bool(self._cached_session),
                    active_request=bool(self._active_request),
                )
                # Use a pre-cached session token if available and fresh,
                # otherwise fetch a new one (HTTP POST to Rumik).
                session = None
                if self._cached_session and (time.monotonic() - self._cached_session_time) < self._SESSION_CACHE_TTL:
                    session = self._cached_session
                    self._cached_session = None
                    _log_rumik_event(
                        "rumik_ws_connect_using_cached_session",
                        source=source,
                        cached_age_s=round(time.monotonic() - self._cached_session_time, 3),
                    )
                if not session:
                    session = await adapter.create_session("init")
                ws_url = session.get("ws_url")
                token = session.get("token")
                if not ws_url or not token:
                    raise RuntimeError(f"Rumik session response missing ws_url/token: {session}")
                self._websocket = await websockets_connect(f"{ws_url}?token={quote(str(token))}")
                self._last_ws_connected_at = time.monotonic()
                self._last_ws_activity_at = self._last_ws_connected_at
                await self._call_event_handler("on_connected")
                _log_rumik_event(
                    "rumik_ws_connect_done",
                    source=source,
                    elapsed_s=round(time.monotonic() - started_at, 3),
                    ws_state=self._websocket_state_name(),
                    replayed_active_request=bool(self._active_request),
                )
                if self._active_request:
                    await self._send_active_request()
                # Start pre-fetching the next session token in the background
                # so the next reconnection is nearly instant.
                if prefetch:
                    self._start_session_prefetch()
            except Exception as exc:
                _log_rumik_event(
                    "rumik_ws_connect_failed",
                    source=source,
                    elapsed_s=round(time.monotonic() - started_at, 3),
                    error=str(exc),
                    ws_state=self._websocket_state_name(),
                )
                self._websocket = None
                self._last_ws_connected_at = None
                self._last_ws_activity_at = None
                # If we used a cached session and it failed, clear it and
                # let the next attempt fetch a fresh one.
                self._cached_session = None
                await self.push_error(error_msg=f"Rumik TTS connection failed: {exc}", exception=exc)
                await self._call_event_handler("on_connection_error", str(exc))

        async def _disconnect_websocket(self):
            _log_rumik_event(
                "rumik_ws_disconnect_start",
                ws_state=self._websocket_state_name(),
                idle_age_s=self._idle_age_s(),
                connection_age_s=self._connection_age_s(),
            )
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
                self._last_ws_connected_at = None
                self._last_ws_activity_at = None
                _log_rumik_event("rumik_ws_disconnect_done")
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
            if self._websocket_keepalive_task:
                await self.cancel_task(self._websocket_keepalive_task)
                self._websocket_keepalive_task = None
            if self._session_prefetch_task:
                self._session_prefetch_task.cancel()
                self._session_prefetch_task = None
            if (
                self._interruption_reconnect_task
                and self._interruption_reconnect_task is not asyncio.current_task()
            ):
                await self.cancel_task(self._interruption_reconnect_task)
                self._interruption_reconnect_task = None
            self._request_queue = asyncio.Queue()
            self._active_request = None
            self._active_done = asyncio.Event()
            self._pending_by_context.clear()
            self._flushed_context_ids.clear()

        def _start_session_prefetch(self):
            """Kick off a background task to pre-fetch the next Rumik session token."""
            if self._session_prefetch_task and not self._session_prefetch_task.done():
                _log_rumik_event("rumik_session_prefetch_skip_running")
                return
            _log_rumik_event("rumik_session_prefetch_start")
            self._session_prefetch_task = self.create_task(self._prefetch_session())

        async def _prefetch_session(self):
            """Pre-fetch a Rumik session token so the next reconnect is near-instant."""
            started_at = time.monotonic()
            try:
                session = await adapter.create_session("init")
                self._cached_session = session
                self._cached_session_time = time.monotonic()
                _log_rumik_event(
                    "rumik_session_prefetch_done",
                    elapsed_s=round(time.monotonic() - started_at, 3),
                    expires_in=session.get("expires_in"),
                    request_id=session.get("request_id"),
                )
            except Exception as exc:
                self._cached_session = None
                _log_rumik_event(
                    "rumik_session_prefetch_failed",
                    elapsed_s=round(time.monotonic() - started_at, 3),
                    error=str(exc),
                )

        def _start_interruption_reconnect(self, context_id: str):
            if self._interruption_reconnect_task and not self._interruption_reconnect_task.done():
                _log_rumik_event("rumik_interruption_reconnect_skip_running", context_id=context_id)
                return
            _log_rumik_event("rumik_interruption_reconnect_start", context_id=context_id)
            self._interruption_reconnect_task = self.create_task(self._reconnect_after_interruption(context_id))

        async def _reconnect_after_interruption(self, context_id: str):
            started_at = time.monotonic()
            try:
                await self._connect()
                _log_rumik_event(
                    "rumik_interruption_reconnect_done",
                    context_id=context_id,
                    elapsed_s=round(time.monotonic() - started_at, 3),
                    ws_state=self._websocket_state_name(),
                    connection_age_s=self._connection_age_s(),
                )
            except asyncio.CancelledError:
                _log_rumik_event(
                    "rumik_interruption_reconnect_cancelled",
                    context_id=context_id,
                    elapsed_s=round(time.monotonic() - started_at, 3),
                )
                raise
            except Exception as exc:
                _log_rumik_event(
                    "rumik_interruption_reconnect_failed",
                    context_id=context_id,
                    elapsed_s=round(time.monotonic() - started_at, 3),
                    error=str(exc),
                    ws_state=self._websocket_state_name(),
                )
            finally:
                if self._interruption_reconnect_task is asyncio.current_task():
                    self._interruption_reconnect_task = None

        async def _await_interruption_reconnect(self):
            task = self._interruption_reconnect_task
            if not task or task.done() or task is asyncio.current_task():
                return
            _log_rumik_event(
                "rumik_interruption_reconnect_wait",
                ws_state=self._websocket_state_name(),
            )
            await task

        def _ensure_sender_task(self):
            if not self._sender_task:
                self._sender_task = self.create_task(self._sender_loop())

        def _ensure_context_keepalive_task(self):
            if not self._context_keepalive_task or self._context_keepalive_task.done():
                self._context_keepalive_task = self.create_task(self._context_keepalive_loop())

        def _ensure_websocket_keepalive_task(self):
            if not self._websocket_keepalive_task or self._websocket_keepalive_task.done():
                self._websocket_keepalive_task = self.create_task(self._websocket_keepalive_loop())

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

        async def _websocket_keepalive_loop(self):
            try:
                while True:
                    await asyncio.sleep(self._websocket_keepalive_interval_s)
                    if self._disconnecting or self._active_request:
                        continue
                    if not self._websocket or self._websocket.state is State.CLOSED:
                        await self._reconnect_websocket_from_keepalive("missing_or_closed")
                        continue
                    try:
                        pong_waiter = await self._get_websocket().ping()
                        latency = await asyncio.wait_for(
                            pong_waiter,
                            timeout=self._websocket_keepalive_timeout_s,
                        )
                        self._last_ws_activity_at = time.monotonic()
                        _log_rumik_event(
                            "rumik_ws_keepalive_pong",
                            latency_s=round(float(latency), 3),
                            ws_state=self._websocket_state_name(),
                            idle_age_s=self._idle_age_s(),
                            connection_age_s=self._connection_age_s(),
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        _log_rumik_event(
                            "rumik_ws_keepalive_failed",
                            error=str(exc),
                            ws_state=self._websocket_state_name(),
                            idle_age_s=self._idle_age_s(),
                            connection_age_s=self._connection_age_s(),
                        )
                        await self._reconnect_websocket_from_keepalive("keepalive_failed")
            except asyncio.CancelledError:
                raise
            finally:
                if self._websocket_keepalive_task is asyncio.current_task():
                    self._websocket_keepalive_task = None

        async def _reconnect_websocket_from_keepalive(self, reason: str) -> None:
            if self._disconnecting:
                return
            _log_rumik_event(
                "rumik_ws_keepalive_reconnect",
                reason=reason,
                ws_state=self._websocket_state_name(),
                idle_age_s=self._idle_age_s(),
                connection_age_s=self._connection_age_s(),
            )
            await self._try_reconnect(report_error=self._report_error)

        def _websocket_refresh_reason_before_send(self) -> str | None:
            if not self._websocket or self._websocket.state is State.CLOSED:
                return "missing_or_closed"
            now = time.monotonic()
            if (
                self._last_ws_activity_at is not None
                and now - self._last_ws_activity_at >= self._websocket_refresh_idle_s
            ):
                return "idle_too_old"
            if (
                self._last_ws_connected_at is not None
                and now - self._last_ws_connected_at >= self._websocket_refresh_connection_age_s
            ):
                return "connection_too_old"
            return None

        async def _send_active_request(self):
            if not self._active_request:
                return
            self._active_request_started_at = time.monotonic()
            self._active_audio_bytes = 0
            _log_rumik_event(
                "rumik_send_text_start",
                context_id=self._active_request.context_id,
                text_chars=len(self._active_request.text),
                ws_state=self._websocket_state_name(),
                idle_age_s=self._idle_age_s(),
                connection_age_s=self._connection_age_s(),
            )
            message = json.dumps({"text": self._active_request.text, "speaker_id": 0})
            await self._get_websocket().send(message)
            self._last_ws_activity_at = time.monotonic()
            _log_rumik_event(
                "rumik_send_text_done",
                context_id=self._active_request.context_id,
                text_chars=len(self._active_request.text),
                ws_state=self._websocket_state_name(),
                idle_age_s=self._idle_age_s(),
                connection_age_s=self._connection_age_s(),
            )

        async def _send_or_reconnect_active_request(self):
            refresh_reason = self._websocket_refresh_reason_before_send()
            if refresh_reason == "missing_or_closed":
                _log_rumik_event(
                    "rumik_reconnect_before_send",
                    reason=refresh_reason,
                    ws_state=self._websocket_state_name(),
                    idle_age_s=self._idle_age_s(),
                    connection_age_s=self._connection_age_s(),
                    active_request=bool(self._active_request),
                )
                await self._connect()
                if not self._websocket:
                    raise RuntimeError("Rumik WebSocket reconnect failed")
                return
            if refresh_reason:
                _log_rumik_event(
                    "rumik_reconnect_before_send",
                    reason=refresh_reason,
                    ws_state=self._websocket_state_name(),
                    idle_age_s=self._idle_age_s(),
                    connection_age_s=self._connection_age_s(),
                    active_request=bool(self._active_request),
                )
                if not await self._try_reconnect(report_error=self._report_error):
                    raise RuntimeError("Rumik WebSocket reconnect failed")
                return
            try:
                await self._send_active_request()
            except Exception as exc:
                _log_rumik_event(
                    "rumik_reconnect_after_send_error",
                    error=str(exc),
                    ws_state=self._websocket_state_name(),
                    idle_age_s=self._idle_age_s(),
                    connection_age_s=self._connection_age_s(),
                    active_request=bool(self._active_request),
                )
                if not await self._try_reconnect(report_error=self._report_error):
                    raise RuntimeError("Rumik WebSocket reconnect failed")

        async def _sender_loop(self):
            try:
                while True:
                    request = await self._request_queue.get()
                    _log_rumik_event(
                        "rumik_sender_request_dequeued",
                        context_id=request.context_id,
                        text_chars=len(request.text),
                        queued_after_get=self._request_queue.qsize(),
                        ws_state=self._websocket_state_name(),
                    )
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
            _log_rumik_event(
                "rumik_request_complete",
                context_id=request.context_id,
                text_chars=len(request.text),
                audio_bytes=self._active_audio_bytes,
                elapsed_since_send_s=self._active_elapsed_s(),
                ws_state=self._websocket_state_name(),
                idle_age_s=self._idle_age_s(),
                connection_age_s=self._connection_age_s(),
            )
            pending = self._pending_by_context.get(request.context_id, 0) - 1
            if pending > 0:
                self._pending_by_context[request.context_id] = pending
            else:
                self._pending_by_context.pop(request.context_id, None)
            self._active_done.set()
            await self._finish_context_if_drained(request.context_id)
            self._active_request_started_at = None
            self._active_audio_bytes = 0

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
                    self._last_ws_activity_at = time.monotonic()
                    if self._active_audio_bytes == 0:
                        _log_rumik_event(
                            "rumik_first_pcm",
                            context_id=request.context_id,
                            chunk_bytes=len(message),
                            elapsed_since_send_s=self._active_elapsed_s(),
                            ws_state=self._websocket_state_name(),
                            connection_age_s=self._connection_age_s(),
                        )
                    self._active_audio_bytes += len(message)
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
                self._last_ws_activity_at = time.monotonic()
                _log_rumik_event(
                    "rumik_done",
                    context_id=request.context_id,
                    request_id=payload.get("request_id"),
                    audio_duration=payload.get("audio_duration"),
                    total_time=payload.get("total_time"),
                    rtf=payload.get("rtf"),
                    total_bytes=payload.get("total_bytes"),
                    credits_used=payload.get("credits_used"),
                    received_audio_bytes=self._active_audio_bytes,
                    elapsed_since_send_s=self._active_elapsed_s(),
                    ws_state=self._websocket_state_name(),
                    connection_age_s=self._connection_age_s(),
                )
                await self._complete_active_request()
            elif message_type == "queued":
                self._last_ws_activity_at = time.monotonic()
                _log_rumik_event(
                    "rumik_queued",
                    context_id=request.context_id if request else None,
                    queue_depth=payload.get("queue_depth"),
                    elapsed_since_send_s=self._active_elapsed_s(),
                    ws_state=self._websocket_state_name(),
                    connection_age_s=self._connection_age_s(),
                )
                return
            elif payload.get("error"):
                self._last_ws_activity_at = time.monotonic()
                _log_rumik_event(
                    "rumik_error_message",
                    context_id=request.context_id if request else None,
                    error=payload.get("error"),
                    elapsed_since_send_s=self._active_elapsed_s(),
                    ws_state=self._websocket_state_name(),
                )
                await self.push_error(error_msg=f"Rumik TTS error: {payload}")
                await self._complete_active_request()

        async def _receive_messages(self):
            async for message in self._get_websocket():
                await self._handle_rumik_message(message)

        async def on_audio_context_interrupted(self, context_id: str):
            _log_rumik_event(
                "rumik_audio_context_interrupted",
                context_id=context_id,
                ws_state=self._websocket_state_name(),
                idle_age_s=self._idle_age_s(),
                connection_age_s=self._connection_age_s(),
                queued_requests=self._request_queue.qsize(),
                active_request=bool(self._active_request),
            )
            await self._disconnect()
            self._start_interruption_reconnect(context_id)
            await super().on_audio_context_interrupted(context_id)

        async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
            try:
                _log_rumik_event(
                    "rumik_run_tts_start",
                    context_id=context_id,
                    text_chars=len(text),
                    ws_state=self._websocket_state_name(),
                    idle_age_s=self._idle_age_s(),
                    connection_age_s=self._connection_age_s(),
                )
                await self._await_interruption_reconnect()
                if not self._websocket or self._websocket.state is State.CLOSED:
                    await self._connect()
                if not self._websocket:
                    raise RuntimeError("Rumik WebSocket is not connected")
                rumik_text = normalize_rumik_text(text)[:2000]
                request = _RumikTTSRequest(text=rumik_text, context_id=context_id)
                self._pending_by_context[context_id] = self._pending_by_context.get(context_id, 0) + 1
                await self._request_queue.put(request)
                _log_rumik_event(
                    "rumik_run_tts_queued",
                    context_id=context_id,
                    text_chars=len(rumik_text),
                    pending_for_context=self._pending_by_context[context_id],
                    queued_requests=self._request_queue.qsize(),
                    ws_state=self._websocket_state_name(),
                )
                self._ensure_sender_task()
                self._ensure_context_keepalive_task()
                await self.start_tts_usage_metrics(text)
                yield None
            except Exception as exc:
                _log_rumik_event(
                    "rumik_run_tts_failed",
                    context_id=context_id,
                    text_chars=len(text),
                    error=str(exc),
                    ws_state=self._websocket_state_name(),
                )
                yield ErrorFrame(error=f"Rumik TTS failed: {exc}")

    return PipecatRumikTTSService()
