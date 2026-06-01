from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from app.pipecat_pipeline.call_context import CallContext

DEFAULT_FRAME_TRACE_PATH = Path("logs") / "frame_trace.jsonl"


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FrameTraceLogger:
    def __init__(
        self,
        context: CallContext,
        *,
        path: str | Path = DEFAULT_FRAME_TRACE_PATH,
        clock: Callable[[], str] = utc_timestamp,
    ) -> None:
        self._context = context
        self._path = Path(path)
        self._clock = clock

    def log(
        self,
        event: str,
        *,
        frame: str | None = None,
        direction: str | None = None,
        turn_id: str | None = None,
        **metadata: Any,
    ) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "timestamp": self._clock(),
            "event": event,
            "frame": frame,
            "direction": direction,
            "session_id": self._context.session_id,
            "call_id": self._context.call_id,
            "turn_id": turn_id,
            "metadata": {key: value for key, value in metadata.items() if value is not None},
        }
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False, default=str, separators=(",", ":")))
            file.write("\n")


def create_frame_trace_processor(
    context: CallContext,
    *,
    trace: FrameTraceLogger | None = None,
    monotonic_clock: Callable[[], float] = time.monotonic,
):
    from pipecat.frames.frames import (
        BotStartedSpeakingFrame,
        BotStoppedSpeakingFrame,
        CancelFrame,
        EndFrame,
        Frame,
        InterimTranscriptionFrame,
        InterruptionFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
        TTSAudioRawFrame,
        TTSStartedFrame,
        TTSStoppedFrame,
        TranscriptionFrame,
        UserStartedSpeakingFrame,
        UserStoppedSpeakingFrame,
        VADUserStartedSpeakingFrame,
        VADUserStoppedSpeakingFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    trace = trace or FrameTraceLogger(context)

    class FrameTraceProcessor(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name="stable_frame_trace")
            self._turn_index = 0
            self._current_turn_id: str | None = None
            self._final_transcript_at: float | None = None
            self._llm_response_started_at: float | None = None
            self._seen_llm_first_token = False
            self._seen_tts_first_audio = False

        def _direction_name(self, direction: FrameDirection) -> str:
            return getattr(direction, "name", str(direction)).lower()

        def _ensure_turn(self) -> str:
            if not self._current_turn_id:
                self._turn_index += 1
                self._current_turn_id = f"turn-{self._turn_index:04d}"
            return self._current_turn_id

        def _start_turn(self) -> str:
            self._turn_index += 1
            self._current_turn_id = f"turn-{self._turn_index:04d}"
            self._final_transcript_at = None
            self._llm_response_started_at = None
            self._seen_llm_first_token = False
            self._seen_tts_first_audio = False
            return self._current_turn_id

        def _latency_ms(self, started_at: float | None, now: float) -> int | None:
            if started_at is None:
                return None
            return max(0, round((now - started_at) * 1000))

        def _log(self, event: str, frame: Frame, direction: FrameDirection, **metadata: Any) -> None:
            trace.log(
                event,
                frame=type(frame).__name__,
                direction=self._direction_name(direction),
                turn_id=self._current_turn_id,
                **metadata,
            )

        async def process_frame(self, frame: Frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            now = monotonic_clock()

            if isinstance(frame, UserStartedSpeakingFrame):
                self._start_turn()
                self._log("user_started_speaking", frame, direction)
            elif isinstance(frame, UserStoppedSpeakingFrame):
                self._ensure_turn()
                self._log("user_stopped_speaking", frame, direction)
            elif isinstance(frame, VADUserStartedSpeakingFrame):
                self._ensure_turn()
                self._log(
                    "vad_started_speaking",
                    frame,
                    direction,
                    start_secs=getattr(frame, "start_secs", None),
                    source_timestamp=getattr(frame, "timestamp", None),
                )
            elif isinstance(frame, VADUserStoppedSpeakingFrame):
                self._ensure_turn()
                self._log(
                    "vad_stopped_speaking",
                    frame,
                    direction,
                    stop_secs=getattr(frame, "stop_secs", None),
                    source_timestamp=getattr(frame, "timestamp", None),
                )
            elif isinstance(frame, InterimTranscriptionFrame):
                self._ensure_turn()
                self._log(
                    "transcription_interim",
                    frame,
                    direction,
                    text=getattr(frame, "text", None),
                    user_id=getattr(frame, "user_id", None),
                    source_timestamp=getattr(frame, "timestamp", None),
                    language=getattr(getattr(frame, "language", None), "value", None),
                )
            elif isinstance(frame, TranscriptionFrame):
                self._ensure_turn()
                self._final_transcript_at = now
                self._log(
                    "transcription_final",
                    frame,
                    direction,
                    text=getattr(frame, "text", None),
                    user_id=getattr(frame, "user_id", None),
                    source_timestamp=getattr(frame, "timestamp", None),
                    language=getattr(getattr(frame, "language", None), "value", None),
                    finalized=getattr(frame, "finalized", None),
                )
            elif isinstance(frame, LLMFullResponseStartFrame):
                self._ensure_turn()
                self._llm_response_started_at = now
                self._seen_llm_first_token = False
                self._seen_tts_first_audio = False
                self._log("llm_response_started", frame, direction)
            elif isinstance(frame, LLMTextFrame):
                self._ensure_turn()
                if not self._seen_llm_first_token:
                    self._seen_llm_first_token = True
                    self._log(
                        "llm_first_token",
                        frame,
                        direction,
                        text=getattr(frame, "text", None),
                        latency_ms=self._latency_ms(self._final_transcript_at, now),
                    )
            elif isinstance(frame, BotStartedSpeakingFrame):
                self._ensure_turn()
                self._log("bot_started_speaking", frame, direction)
            elif isinstance(frame, BotStoppedSpeakingFrame):
                self._ensure_turn()
                self._log("bot_stopped_speaking", frame, direction)
            elif isinstance(frame, TTSStartedFrame):
                self._ensure_turn()
                self._log("tts_started", frame, direction, context_id=getattr(frame, "context_id", None))
            elif isinstance(frame, TTSAudioRawFrame):
                self._ensure_turn()
                if not self._seen_tts_first_audio:
                    self._seen_tts_first_audio = True
                    self._log(
                        "tts_first_audio",
                        frame,
                        direction,
                        latency_ms=self._latency_ms(self._llm_response_started_at, now),
                        context_id=getattr(frame, "context_id", None),
                        bytes=len(getattr(frame, "audio", b"") or b""),
                        sample_rate=getattr(frame, "sample_rate", None),
                        num_channels=getattr(frame, "num_channels", None),
                    )
            elif isinstance(frame, TTSStoppedFrame):
                self._ensure_turn()
                self._log("tts_stopped", frame, direction, context_id=getattr(frame, "context_id", None))
            elif isinstance(frame, InterruptionFrame):
                self._ensure_turn()
                self._log("interruption", frame, direction, reason="interruption_frame")
            elif isinstance(frame, EndFrame):
                self._log("end_of_call", frame, direction, reason=getattr(frame, "reason", None))
            elif isinstance(frame, CancelFrame):
                self._log("end_of_call", frame, direction, reason=getattr(frame, "reason", None) or "cancelled")

            await self.push_frame(frame, direction)

    return FrameTraceProcessor()
