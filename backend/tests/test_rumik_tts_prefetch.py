import asyncio
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from pipecat.frames.frames import TTSAudioRawFrame, TTSStoppedFrame
from pipecat.services.tts_service import WebsocketTTSService
from websockets.protocol import State

from app.pipecat_pipeline.rumik_tts import RumikTTSService, create_pipecat_rumik_tts_service


async def exhaust(generator):
    return [frame async for frame in generator]


async def wait_for_condition(condition, *, attempts: int = 10) -> None:
    for _ in range(attempts):
        if condition():
            return
        await asyncio.sleep(0)


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.pings = 0
        self.closed = False
        self.state = State.OPEN

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def ping(self):
        self.pings += 1
        done = asyncio.get_running_loop().create_future()
        done.set_result(0.001)
        return done

    async def close(self) -> None:
        self.closed = True


class AlreadyClosedWebSocket(FakeWebSocket):
    async def send(self, message: str) -> None:
        raise RuntimeError("socket already closed")


class PingFailingWebSocket(FakeWebSocket):
    async def ping(self):
        raise RuntimeError("ping failed")


class ClosingWebSocket(FakeWebSocket):
    def __init__(self) -> None:
        super().__init__()
        self.state = State.CLOSING


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

    async def test_preconnect_opens_socket_without_sending_speech(self) -> None:
        self.service._websocket = None
        self.service._call_event_handler = AsyncMock()
        self.service._receive_task_handler = AsyncMock()
        self.adapter.create_session = AsyncMock(return_value={"ws_url": "wss://rumik.test/ws", "token": "token"})
        socket = FakeWebSocket()

        with patch("app.pipecat_pipeline.rumik_tts.websockets_connect", AsyncMock(return_value=socket)) as connect:
            await self.service.preconnect()

        self.assertIs(self.service._websocket, socket)
        self.assertEqual([], socket.sent)
        self.adapter.create_session.assert_awaited_once_with("init")
        connect.assert_awaited_once_with("wss://rumik.test/ws?token=token")

    async def test_preconnect_does_not_create_pipecat_managed_tasks_before_start(self) -> None:
        self.service._websocket = None
        self.service._call_event_handler = AsyncMock()
        self.service.create_task = Mock(side_effect=AssertionError("TaskManager should not be used during preconnect"))
        self.adapter.create_session = AsyncMock(return_value={"ws_url": "wss://rumik.test/ws", "token": "token"})

        with patch("app.pipecat_pipeline.rumik_tts.websockets_connect", AsyncMock(return_value=FakeWebSocket())):
            await self.service.preconnect()

        self.service.create_task.assert_not_called()

    async def test_websocket_keepalive_pings_idle_open_socket(self) -> None:
        self.service._websocket_keepalive_interval_s = 0
        self.service._websocket_keepalive_timeout_s = 0.1

        self.service._ensure_websocket_keepalive_task()
        await wait_for_condition(lambda: self.socket.pings >= 1)

        self.assertGreaterEqual(self.socket.pings, 1)

    async def test_websocket_keepalive_reconnects_when_ping_fails(self) -> None:
        self.service._websocket = PingFailingWebSocket()
        self.service._websocket_keepalive_interval_s = 0
        self.service._websocket_keepalive_timeout_s = 0.1
        self.service._try_reconnect = AsyncMock(return_value=True)

        self.service._ensure_websocket_keepalive_task()
        await wait_for_condition(lambda: self.service._try_reconnect.await_count >= 1)

        self.service._try_reconnect.assert_awaited()

    async def test_stale_socket_reconnects_before_sending_speech(self) -> None:
        self.service._active_request = SimpleNamespace(text="[neutral] Namaste.", context_id="turn-1")
        self.service._websocket_refresh_idle_s = 10.0
        self.service._last_ws_activity_at = time.monotonic() - 11.0
        self.service._try_reconnect = AsyncMock(return_value=True)
        self.service._receive_task_handler = AsyncMock()

        await self.service._send_or_reconnect_active_request()

        self.service._try_reconnect.assert_awaited()
        self.assertEqual([], self.socket.sent)

    async def test_closing_socket_reconnects_before_sending_speech(self) -> None:
        closing_socket = ClosingWebSocket()
        self.service._websocket = closing_socket
        self.service._active_request = SimpleNamespace(text="[neutral] Namaste.", context_id="turn-1")
        self.service._try_reconnect = AsyncMock(return_value=True)
        self.service._receive_task_handler = AsyncMock()

        await self.service._send_or_reconnect_active_request()

        self.service._try_reconnect.assert_awaited()
        self.assertEqual([], closing_socket.sent)

    async def test_sender_side_reconnect_restarts_finished_receive_task(self) -> None:
        finished_receive_task = asyncio.create_task(asyncio.sleep(0))
        await finished_receive_task
        self.service._receive_task = finished_receive_task
        self.service._receive_task_handler = AsyncMock()
        self.service._active_request = SimpleNamespace(text="[neutral] Namaste.", context_id="turn-1")
        self.service._last_ws_activity_at = time.monotonic() - 11.0
        self.service._websocket_refresh_idle_s = 10.0
        self.service._try_reconnect = AsyncMock(return_value=True)

        await self.service._send_or_reconnect_active_request()

        self.service._receive_task_handler.assert_called_once_with(self.service._report_error)
        self.assertIsNot(self.service._receive_task, finished_receive_task)

    async def test_sentence_requests_reuse_socket_and_send_in_order(self) -> None:
        await exhaust(self.service.run_tts("Pehla sentence.", "turn-1"))
        await exhaust(self.service.run_tts("Doosra sentence.", "turn-1"))
        await asyncio.sleep(0)

        self.assertEqual(
            [{"text": "[neutral] Pehla sentence.", "speaker_id": 0}],
            [json.loads(message) for message in self.socket.sent],
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

    async def test_active_request_keeps_context_alive_while_waiting_for_pcm(self) -> None:
        self.service.audio_context_available = lambda _context_id: True
        self.service._refresh_audio_context = Mock()
        self.service._context_keepalive_interval_s = 0
        await exhaust(self.service.run_tts("Namaste.", "turn-1"))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        self.service._refresh_audio_context.assert_called_with("turn-1")

    async def test_interruption_drops_queued_sentences_and_closes_socket(self) -> None:
        self.service._disconnect_websocket = AsyncMock()
        await exhaust(self.service.run_tts("Pehla sentence.", "turn-1"))
        await exhaust(self.service.run_tts("Doosra sentence.", "turn-1"))
        await asyncio.sleep(0)

        await self.service.on_audio_context_interrupted("turn-1")

        self.service._disconnect_websocket.assert_awaited_once()
        self.assertEqual(0, self.service._request_queue.qsize())
        self.assertIsNone(self.service._active_request)

    async def test_interruption_starts_background_reconnect_for_next_turn(self) -> None:
        self.service._disconnect_websocket = AsyncMock()
        await exhaust(self.service.run_tts("Pehla sentence.", "turn-1"))
        await asyncio.sleep(0)

        await self.service.on_audio_context_interrupted("turn-1")
        await asyncio.sleep(0)

        self.service._connect.assert_awaited_once()

    async def test_disconnect_sends_graceful_close_message(self) -> None:
        self.service.stop_all_metrics = AsyncMock()
        self.service._call_event_handler = AsyncMock()

        await self.service._disconnect_websocket()

        self.assertEqual({"type": "close"}, json.loads(self.socket.sent[-1]))
        self.assertTrue(self.socket.closed)

    async def test_disconnect_tolerates_socket_that_server_already_closed(self) -> None:
        socket = AlreadyClosedWebSocket()
        self.service._websocket = socket
        self.service.stop_all_metrics = AsyncMock()
        self.service._call_event_handler = AsyncMock()

        await self.service._disconnect_websocket()

        self.assertTrue(socket.closed)
        self.assertIsNone(self.service._websocket)


class PipecatRumikWiringTests(unittest.TestCase):
    def test_rumik_tts_explicitly_buffers_complete_sentences(self) -> None:
        source = Path("app/pipecat_pipeline/rumik_tts.py").read_text(encoding="utf-8")

        self.assertIn("text_aggregation_mode=TextAggregationMode.SENTENCE", source)

    def test_bot_uses_persistent_service_with_parallel_rumik_preconnect(self) -> None:
        source = Path("app/pipecat_pipeline/bot.py").read_text(encoding="utf-8")

        self.assertIn("rumik_preconnect_task = asyncio.create_task(tts.preconnect())", source)
        self.assertIn("rumik_preconnect_task.add_done_callback", source)
        self.assertNotIn("await rumik_preconnect_task", source)


if __name__ == "__main__":
    unittest.main()
