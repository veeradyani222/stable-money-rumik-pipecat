from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from app.pipecat_pipeline.call_context import CallContext
from app.pipecat_pipeline.frame_trace import FrameTraceLogger, create_frame_trace_processor


class FrameTraceLoggerTests(unittest.TestCase):
    def test_writer_appends_jsonl_rows_with_call_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "logs" / "frame_trace.jsonl"
            context = CallContext(session_id="session-1234567890", call_id="call-abc", persona={})
            trace = FrameTraceLogger(context, path=path, clock=lambda: "2026-06-02T00:00:00.000Z")

            trace.log("end_of_call", reason="client_disconnected")

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(1, len(rows))
            self.assertEqual("2026-06-02T00:00:00.000Z", rows[0]["timestamp"])
            self.assertEqual("end_of_call", rows[0]["event"])
            self.assertEqual("session-1234567890", rows[0]["session_id"])
            self.assertEqual("call-abc", rows[0]["call_id"])
            self.assertEqual("client_disconnected", rows[0]["metadata"]["reason"])

    def test_writer_keeps_many_calls_in_one_append_only_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "logs" / "frame_trace.jsonl"
            first = FrameTraceLogger(
                CallContext(session_id="session-a", call_id="call-a", persona={}),
                path=path,
                clock=lambda: "2026-06-02T00:00:00.000Z",
            )
            second = FrameTraceLogger(
                CallContext(session_id="session-b", call_id="call-b", persona={}),
                path=path,
                clock=lambda: "2026-06-02T00:00:01.000Z",
            )

            first.log("user_started_speaking")
            second.log("user_started_speaking")

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["call-a", "call-b"], [row["call_id"] for row in rows])


class FrameTraceProcessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_processor_logs_required_turn_timeline_events(self) -> None:
        from pipecat.frames.frames import (
            BotStartedSpeakingFrame,
            BotStoppedSpeakingFrame,
            EndFrame,
            InterimTranscriptionFrame,
            InterruptionFrame,
            LLMFullResponseStartFrame,
            LLMTextFrame,
            TTSAudioRawFrame,
            TranscriptionFrame,
            UserStartedSpeakingFrame,
            UserStoppedSpeakingFrame,
            VADUserStartedSpeakingFrame,
            VADUserStoppedSpeakingFrame,
        )
        from pipecat.processors.frame_processor import FrameDirection

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame_trace.jsonl"
            context = CallContext(session_id="session-1234567890", call_id="call-abc", persona={})
            now = iter(
                [
                    "2026-06-02T00:00:00.000Z",
                    "2026-06-02T00:00:00.100Z",
                    "2026-06-02T00:00:00.200Z",
                    "2026-06-02T00:00:00.300Z",
                    "2026-06-02T00:00:00.400Z",
                    "2026-06-02T00:00:00.500Z",
                    "2026-06-02T00:00:00.700Z",
                    "2026-06-02T00:00:00.900Z",
                    "2026-06-02T00:00:01.000Z",
                    "2026-06-02T00:00:01.200Z",
                    "2026-06-02T00:00:01.400Z",
                    "2026-06-02T00:00:01.500Z",
                    "2026-06-02T00:00:01.600Z",
                ]
            )
            monotonic_values = iter(
                [0.0, 0.1, 0.2, 0.3, 0.4, 0.7, 0.9, 1.0, 1.2, 1.4, 1.5, 1.6, 1.7]
            )
            trace = FrameTraceLogger(context, path=path, clock=lambda: next(now))
            processor = create_frame_trace_processor(
                context,
                trace=trace,
                monotonic_clock=lambda: next(monotonic_values),
            )
            processor.push_frame = AsyncMock()  # type: ignore[method-assign]
            processor._start_interruption = AsyncMock()  # type: ignore[method-assign]

            await processor.process_frame(UserStartedSpeakingFrame(), FrameDirection.UPSTREAM)
            await processor.process_frame(VADUserStartedSpeakingFrame(start_secs=0.2), FrameDirection.UPSTREAM)
            await processor.process_frame(
                InterimTranscriptionFrame("pay", "user-1", "source-ts"),
                FrameDirection.UPSTREAM,
            )
            await processor.process_frame(UserStoppedSpeakingFrame(), FrameDirection.UPSTREAM)
            await processor.process_frame(VADUserStoppedSpeakingFrame(stop_secs=0.8), FrameDirection.UPSTREAM)
            await processor.process_frame(
                TranscriptionFrame("payment failed", "user-1", "source-ts", finalized=True),
                FrameDirection.UPSTREAM,
            )
            await processor.process_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
            await processor.process_frame(LLMTextFrame("Let me check."), FrameDirection.DOWNSTREAM)
            await processor.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
            await processor.process_frame(TTSAudioRawFrame(b"1234", 24000, 1), FrameDirection.DOWNSTREAM)
            await processor.process_frame(BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
            await processor.process_frame(InterruptionFrame(), FrameDirection.UPSTREAM)
            await processor.process_frame(EndFrame(reason="test complete"), FrameDirection.DOWNSTREAM)

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            events = [row["event"] for row in rows]

            self.assertEqual(
                [
                    "user_started_speaking",
                    "vad_started_speaking",
                    "transcription_interim",
                    "user_stopped_speaking",
                    "vad_stopped_speaking",
                    "transcription_final",
                    "llm_response_started",
                    "llm_first_token",
                    "bot_started_speaking",
                    "tts_first_audio",
                    "bot_stopped_speaking",
                    "interruption",
                    "end_of_call",
                ],
                events,
            )
            self.assertEqual("turn-0001", rows[0]["turn_id"])
            self.assertEqual("turn-0001", rows[7]["turn_id"])
            self.assertEqual("payment failed", rows[5]["metadata"]["text"])
            self.assertEqual("Let me check.", rows[7]["metadata"]["text"])
            self.assertEqual(300, rows[7]["metadata"]["latency_ms"])
            self.assertEqual(500, rows[9]["metadata"]["latency_ms"])
            self.assertEqual("test complete", rows[-1]["metadata"]["reason"])


if __name__ == "__main__":
    unittest.main()
