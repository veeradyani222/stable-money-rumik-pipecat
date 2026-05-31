# Persistent Rumik Pipecat WebSocket Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse one Rumik WebSocket across sentence-sized Pipecat TTS requests so multi-sentence replies keep early first audio without paying a new HTTP session and WebSocket handshake between sentences.

**Architecture:** Replace the one-shot Rumik PCM generator with a custom Pipecat `WebsocketTTSService`. Keep Pipecat's default sentence aggregation, serialize complete Rumik sentence requests over one reusable socket, and keep the shared Pipecat turn audio context open until every queued sentence for that turn reaches Rumik `done`.

**Tech Stack:** Python 3.14, Pipecat 1.3.0, `websockets`, `httpx`, `unittest`, `pytest`.

---

## File Structure

- Modify: `backend/app/pipecat_pipeline/rumik_tts.py`
  - Keep the Rumik session-token HTTP request.
  - Replace one-shot websocket streaming and opening prefetch state with a Pipecat `WebsocketTTSService`.
  - Add FIFO sentence scheduling, PCM routing, turn-context drain tracking, graceful close, and lazy reconnect after interruption.
- Modify: `backend/app/pipecat_pipeline/bot.py`
  - Remove the separate opening prefetch task and its disconnect cleanup.
  - Continue queueing the opening through Pipecat `TTSSpeakFrame`.
- Replace: `backend/tests/test_rumik_tts_prefetch.py`
  - Remove tests for the superseded one-shot prefetch path.
  - Add behavior tests for persistent Pipecat websocket reuse and context lifetime.
- Verify: `backend/tests/test_pipecat_pipeline_order.py`
  - Keep the existing pipeline-order test unchanged.

### Task 1: Add Persistent WebSocket Regression Tests

**Files:**
- Replace: `backend/tests/test_rumik_tts_prefetch.py`
- Test: `backend/app/pipecat_pipeline/rumik_tts.py`

- [ ] **Step 1: Replace the prefetch tests with failing persistent-service tests**

Replace `backend/tests/test_rumik_tts_prefetch.py` with:

```python
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pipecat.frames.frames import TTSAudioRawFrame, TTSStoppedFrame
from pipecat.services.tts_service import WebsocketTTSService
from websockets.protocol import State

from app.pipecat_pipeline.rumik_tts import (
    RumikTTSService,
    create_pipecat_rumik_tts_service,
)


async def exhaust(generator):
    return [frame async for frame in generator]


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False
        self.state = State.OPEN

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def close(self) -> None:
        self.closed = True


class PersistentPipecatRumikTTSTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.adapter = RumikTTSService.__new__(RumikTTSService)
        self.adapter.settings = SimpleNamespace(rumik_tts_model="muga")
        self.socket = FakeWebSocket()
        self.service = create_pipecat_rumik_tts_service(adapter=self.adapter)
        self.service._websocket = self.socket
        self.service._connect = AsyncMock()
        self.service.create_task = lambda coroutine: asyncio.create_task(coroutine)

        async def cancel_task(task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.service.cancel_task = cancel_task

    async def asyncTearDown(self) -> None:
        await self.service._clear_request_state()

    def test_factory_returns_pipecat_websocket_tts_service(self) -> None:
        self.assertIsInstance(self.service, WebsocketTTSService)

    async def test_connect_bootstraps_only_one_socket_while_it_remains_open(self) -> None:
        self.service._websocket = None
        self.service._call_event_handler = AsyncMock()
        self.adapter.create_session = AsyncMock(return_value={"ws_url": "wss://rumik.test/ws", "token": "token"})
        socket = FakeWebSocket()

        with patch("app.pipecat_pipeline.rumik_tts.websockets_connect", AsyncMock(return_value=socket)) as connect:
            await self.service._connect_websocket()
            await self.service._connect_websocket()

        self.adapter.create_session.assert_awaited_once_with("init")
        connect.assert_awaited_once_with("wss://rumik.test/ws?token=token")

    async def test_sentence_requests_reuse_socket_and_send_in_order(self) -> None:
        await exhaust(self.service.run_tts("Pehla sentence.", "turn-1"))
        await exhaust(self.service.run_tts("Doosra sentence.", "turn-1"))
        await asyncio.sleep(0)

        self.assertEqual(
            [{"text": "[neutral] Pehla sentence.", "speaker_id": 0}],
            [json.loads(message) for message in self.socket.sent],
        )

    async def test_reconnect_replays_active_sentence(self) -> None:
        self.service._websocket = None
        self.service._call_event_handler = AsyncMock()
        self.adapter.create_session = AsyncMock(return_value={"ws_url": "wss://rumik.test/ws", "token": "token"})
        self.service._active_request = SimpleNamespace(text="[neutral] Namaste.", context_id="turn-1")
        socket = FakeWebSocket()

        with patch("app.pipecat_pipeline.rumik_tts.websockets_connect", AsyncMock(return_value=socket)):
            await self.service._connect_websocket()

        self.assertEqual(
            [{"text": "[neutral] Namaste.", "speaker_id": 0}],
            [json.loads(message) for message in socket.sent],
        )

        await self.service._handle_rumik_message(json.dumps({"type": "done"}))
        await asyncio.sleep(0)

        self.assertEqual(
            [
                {"text": "[neutral] Pehla sentence.", "speaker_id": 0},
                {"text": "[neutral] Doosra sentence.", "speaker_id": 0},
            ],
            [json.loads(message) for message in self.socket.sent],
        )

    async def test_binary_pcm_is_appended_to_active_pipecat_context(self) -> None:
        self.service.append_to_audio_context = AsyncMock()
        await exhaust(self.service.run_tts("Namaste.", "turn-1"))
        await asyncio.sleep(0)

        await self.service._handle_rumik_message(b"pcm")

        frame = self.service.append_to_audio_context.await_args.args[1]
        self.assertEqual("turn-1", self.service.append_to_audio_context.await_args.args[0])
        self.assertIsInstance(frame, TTSAudioRawFrame)
        self.assertEqual(b"pcm", frame.audio)

    async def test_flushed_context_stops_only_after_last_sentence_done(self) -> None:
        self.service.append_to_audio_context = AsyncMock()
        self.service.remove_audio_context = AsyncMock()
        self.service.audio_context_available = lambda _context_id: True
        await exhaust(self.service.run_tts("Pehla sentence.", "turn-1"))
        await exhaust(self.service.run_tts("Doosra sentence.", "turn-1"))
        await asyncio.sleep(0)
        await self.service.flush_audio("turn-1")

        await self.service._handle_rumik_message(json.dumps({"type": "done"}))
        await asyncio.sleep(0)
        self.assertEqual(0, self.service.remove_audio_context.await_count)

        await self.service._handle_rumik_message(json.dumps({"type": "done"}))
        await asyncio.sleep(0)

        stop_frame = self.service.append_to_audio_context.await_args_list[-1].args[1]
        self.assertIsInstance(stop_frame, TTSStoppedFrame)
        self.service.remove_audio_context.assert_awaited_once_with("turn-1")

    async def test_interruption_drops_queued_sentences_and_closes_socket(self) -> None:
        self.service._disconnect = AsyncMock()
        await exhaust(self.service.run_tts("Pehla sentence.", "turn-1"))
        await exhaust(self.service.run_tts("Doosra sentence.", "turn-1"))
        await asyncio.sleep(0)

        await self.service.on_audio_context_interrupted("turn-1")

        self.service._disconnect.assert_awaited_once()
        self.assertEqual(0, self.service._request_queue.qsize())
        self.assertIsNone(self.service._active_request)

    async def test_disconnect_sends_graceful_close_message(self) -> None:
        self.service.stop_all_metrics = AsyncMock()
        self.service._call_event_handler = AsyncMock()

        await self.service._disconnect_websocket()

        self.assertEqual({"type": "close"}, json.loads(self.socket.sent[-1]))
        self.assertTrue(self.socket.closed)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_rumik_tts_prefetch.py -q
```

Expected: FAIL because `create_pipecat_rumik_tts_service()` does not accept
`adapter=`, returns a plain `TTSService`, and does not expose the persistent
request lifecycle methods.

### Task 2: Implement The Pipecat WebSocket TTS Service

**Files:**
- Modify: `backend/app/pipecat_pipeline/rumik_tts.py`
- Test: `backend/tests/test_rumik_tts_prefetch.py`

- [ ] **Step 1: Replace the one-shot websocket implementation**

Keep `RumikTTSService.create_session()` as the authenticated HTTP bootstrap.
Remove `_PREFETCH_DONE`, `_PrefetchFailed`, `_ensure_prefetch_state()`,
`cancel_prewarm()`, `_stream_pcm_chunks()`, `prewarm()`, and `pcm_chunks()`.

Add imports:

```python
import asyncio
import json
from collections import deque
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from websockets.asyncio.client import connect as websockets_connect
from websockets.protocol import State
```

Add a request record below `RUMIK_SAMPLE_RATE`:

```python
@dataclass(frozen=True)
class _RumikTTSRequest:
    text: str
    context_id: str
```

Change the service factory signature:

```python
def create_pipecat_rumik_tts_service(adapter: RumikTTSService | None = None):
```

Import Pipecat websocket lifecycle classes and frames inside the factory:

```python
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
```

Replace `PipecatRumikTTSService(TTSService)` with:

```python
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
            self._request_queue: asyncio.Queue[_RumikTTSRequest] = asyncio.Queue()
            self._active_request: _RumikTTSRequest | None = None
            self._active_done = asyncio.Event()
            self._pending_by_context: dict[str, int] = {}
            self._flushed_context_ids: set[str] = set()

        def can_generate_metrics(self) -> bool:
            return True

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
                    await self._websocket.send(json.dumps({"type": "close"}))
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
            self._request_queue = asyncio.Queue()
            self._active_request = None
            self._active_done = asyncio.Event()
            self._pending_by_context.clear()
            self._flushed_context_ids.clear()

        def _ensure_sender_task(self):
            if not self._sender_task:
                self._sender_task = self.create_task(self._sender_loop())

        async def _send_active_request(self):
            if not self._active_request:
                return
            message = json.dumps({"text": self._active_request.text, "speaker_id": 0})
            await self._get_websocket().send(message)

        async def _sender_loop(self):
            try:
                while True:
                    request = await self._request_queue.get()
                    self._active_request = request
                    self._active_done.clear()
                    if not self._websocket or self._websocket.state is State.CLOSED:
                        await self._connect()
                    else:
                        try:
                            await self._send_active_request()
                        except Exception:
                            await self._try_reconnect(report_error=self._report_error)
                    await self._active_done.wait()
                    self._active_request = None
                    self._request_queue.task_done()
            except asyncio.CancelledError:
                raise
            finally:
                self._sender_task = None

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
                pending = self._pending_by_context.get(request.context_id, 0) - 1
                if pending > 0:
                    self._pending_by_context[request.context_id] = pending
                else:
                    self._pending_by_context.pop(request.context_id, None)
                self._active_done.set()
                await self._finish_context_if_drained(request.context_id)
            elif message_type == "queued":
                return
            elif payload.get("error"):
                await self.push_error(error_msg=f"Rumik TTS error: {payload}")

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
                rumik_text = normalize_rumik_text(text)[:2000]
                request = _RumikTTSRequest(text=rumik_text, context_id=context_id)
                self._pending_by_context[context_id] = self._pending_by_context.get(context_id, 0) + 1
                await self._request_queue.put(request)
                self._ensure_sender_task()
                await self.start_tts_usage_metrics(text)
                yield None
            except Exception as exc:
                yield ErrorFrame(error=f"Rumik TTS failed: {exc}")
```

Do not add token aggregation. The inherited Pipecat sentence mode is required.

- [ ] **Step 2: Run the focused persistent-service tests to verify GREEN**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_rumik_tts_prefetch.py -q
```

Expected: PASS.

- [ ] **Step 3: Review the implementation against Pipecat context reuse**

Confirm:

- `run_tts()` queues sentence requests and yields `None`, allowing Pipecat to
  continue processing LLM frames.
- `_sender_loop()` sends the next complete sentence only after Rumik `done`.
- `flush_audio()` marks the shared Pipecat turn context as ready to close.
- `_finish_context_if_drained()` emits one `TTSStoppedFrame` only after all
  sentence requests associated with the shared context are done.

### Task 3: Remove Superseded Opening Prefetch Wiring

**Files:**
- Modify: `backend/app/pipecat_pipeline/bot.py`
- Test: `backend/tests/test_rumik_tts_prefetch.py`

- [ ] **Step 1: Add a failing bot-wiring regression test**

Append to `backend/tests/test_rumik_tts_prefetch.py`:

```python
from pathlib import Path


class PipecatRumikWiringTests(unittest.TestCase):
    def test_bot_uses_persistent_service_without_parallel_opening_prefetch(self) -> None:
        source = Path("app/pipecat_pipeline/bot.py").read_text(encoding="utf-8")

        self.assertNotIn("tts.prewarm(", source)
        self.assertNotIn("tts.cancel_prewarm()", source)
        self.assertNotIn("opening_prewarm_task", source)
```

- [ ] **Step 2: Run the wiring test to verify RED**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_rumik_tts_prefetch.py::PipecatRumikWiringTests -q
```

Expected: FAIL because `bot.py` still starts and cancels
`opening_prewarm_task`.

- [ ] **Step 3: Remove the prefetch task from the bot**

In `backend/app/pipecat_pipeline/bot.py`:

- Remove `import asyncio`.
- Remove:

```python
    opening_prewarm_task = asyncio.create_task(tts.prewarm(STABLE_DEFAULT_OPENING))
```

- Remove from `on_client_disconnected()`:

```python
        opening_prewarm_task.cancel()
        tts.cancel_prewarm()
```

Keep:

```python
        await worker.cancel()
```

- [ ] **Step 4: Run the focused TTS tests to verify GREEN**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_rumik_tts_prefetch.py -q
```

Expected: PASS.

### Task 4: Verify Pipecat Pipeline Behavior

**Files:**
- Verify: `backend/app/pipecat_pipeline/rumik_tts.py`
- Verify: `backend/app/pipecat_pipeline/bot.py`
- Verify: `backend/tests/test_rumik_tts_prefetch.py`
- Verify: `backend/tests/test_pipecat_pipeline_order.py`

- [ ] **Step 1: Run focused Pipecat tests**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_rumik_tts_prefetch.py tests/test_pipecat_pipeline_order.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the backend test suite**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

Expected: PASS with zero failures.

- [ ] **Step 3: Review the scoped diff**

Run:

```powershell
git diff -- backend/app/pipecat_pipeline/rumik_tts.py backend/app/pipecat_pipeline/bot.py backend/tests/test_rumik_tts_prefetch.py
```

Confirm:

- The TTS provider adapter is now a Pipecat `WebsocketTTSService`.
- A single Rumik WebSocket is reused for queued sentence requests.
- Shared Pipecat turn contexts close only after their last queued sentence.
- Opening prefetch wiring is removed.
- No frontend files were modified for this fix.
