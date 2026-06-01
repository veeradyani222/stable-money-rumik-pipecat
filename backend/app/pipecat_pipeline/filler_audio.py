from __future__ import annotations

import asyncio
import random
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FILLER_AUDIO_DIR = Path(__file__).resolve().parents[1] / "assets" / "audio"
FILLER_AUDIO_FILENAMES = {
    "payment.failed": "rumik-filler-payment-failed.wav",
    "fd.book.status": "rumik-filler-fd-book-status.wav",
    "fd.withdraw.premature": "rumik-filler-fd-withdraw-premature.wav",
    "kyc.status": "rumik-filler-kyc-status.wav",
    "kyc.explainer": "rumik-filler-kyc-explainer.wav",
    "fd.rates.compare": "rumik-filler-fd-rates-compare.wav",
    "maturity.payout.delay": "rumik-filler-maturity-payout-delay.wav",
    "app.real.check": "rumik-filler-app-real-check.wav",
    "ticket.status": "rumik-filler-ticket-status.wav",
    "grievance.escalate": "rumik-filler-grievance-escalate.wav",
    "support.contact": "rumik-filler-support-contact.wav",
    "payment.summary": "rumik-filler-payment-summary.wav",
    "fd.summary": "rumik-filler-fd-summary.wav",
    "account.overview": "rumik-filler-account-overview.wav",
    "refund.status": "rumik-filler-refund-status.wav",
    "secure.action.help": "rumik-filler-secure-action-help.wav",
    "unknown": (
        "rumik-filler-unknown.wav",
        "rumik-filler-unknown-2.wav",
        "rumik-filler-unknown-3.wav",
        "rumik-filler-unknown-4.wav",
    ),
}


@dataclass(frozen=True)
class FillerAudio:
    filename: str
    pcm: bytes
    sample_rate: int
    num_channels: int


StructuredLogEvent = Callable[..., None]


def _filler_audio_filename_for_intent(intent: str, *, exclude_filename: str | None = None) -> str | None:
    if intent == "conversation.goodbye":
        return None
    configured = FILLER_AUDIO_FILENAMES.get(intent, FILLER_AUDIO_FILENAMES["unknown"])
    if not isinstance(configured, tuple):
        return configured
    candidates = configured
    if exclude_filename and len(configured) > 1:
        candidates = tuple(filename for filename in configured if filename != exclude_filename)
    return random.choice(candidates)


def filler_audio_path_for_intent(intent: str, *, exclude_filename: str | None = None) -> Path | None:
    filename = _filler_audio_filename_for_intent(intent, exclude_filename=exclude_filename)
    return FILLER_AUDIO_DIR / filename if filename else None


def load_filler_audio_from_path(path: Path) -> FillerAudio:
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2:
            raise ValueError(f"Filler audio must be 16-bit PCM: {path}")
        return FillerAudio(
            filename=path.name,
            pcm=wav.readframes(wav.getnframes()),
            sample_rate=wav.getframerate(),
            num_channels=wav.getnchannels(),
        )


def load_filler_audio_for_intent(intent: str, *, exclude_filename: str | None = None) -> FillerAudio | None:
    path = filler_audio_path_for_intent(intent, exclude_filename=exclude_filename)
    if not path:
        return None
    return load_filler_audio_from_path(path)


class FillerAudioPlayer:
    def __init__(self, *, output: Any, context: Any, log_event: StructuredLogEvent) -> None:
        self._output = output
        self._context = context
        self._log_event = log_event
        self._last_filename_by_intent: dict[str, str] = {}

    def start(self, intent: str) -> asyncio.Task[None]:
        return asyncio.create_task(self._queue(intent))

    async def _queue(self, intent: str) -> None:
        last_filename = self._last_filename_by_intent.get(intent)
        path = filler_audio_path_for_intent(intent, exclude_filename=last_filename)
        audio: FillerAudio | None = None
        try:
            if path:
                audio = load_filler_audio_from_path(path)
            if not audio:
                self._log_event(
                    "voice_filler_skipped",
                    session_id=self._context.session_id,
                    call_id=self._context.call_id,
                    intent=intent,
                    reason="conversation_goodbye",
                )
                return
            from pipecat.frames.frames import TTSAudioRawFrame, TTSStoppedFrame

            self._log_event(
                "voice_filler_started",
                session_id=self._context.session_id,
                call_id=self._context.call_id,
                intent=intent,
                filename=audio.filename,
                audio_bytes=len(audio.pcm),
            )
            await self._output.queue_frame(
                TTSAudioRawFrame(audio.pcm, audio.sample_rate, audio.num_channels)
            )
            await self._output.queue_frame(TTSStoppedFrame())
            self._log_event(
                "voice_filler_queued",
                session_id=self._context.session_id,
                call_id=self._context.call_id,
                intent=intent,
                filename=audio.filename,
                audio_bytes=len(audio.pcm),
            )
            self._last_filename_by_intent[intent] = audio.filename
        except Exception as exc:
            self._log_event(
                "voice_filler_failed",
                session_id=self._context.session_id,
                call_id=self._context.call_id,
                intent=intent,
                filename=audio.filename if audio else path.name if path else None,
                error=str(exc),
            )


def create_filler_audio_player(*, output: Any, context: Any, log_event: StructuredLogEvent) -> FillerAudioPlayer:
    return FillerAudioPlayer(output=output, context=context, log_event=log_event)
