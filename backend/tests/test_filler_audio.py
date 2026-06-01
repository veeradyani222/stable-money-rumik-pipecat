from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from pipecat.frames.frames import TTSAudioRawFrame, TTSStoppedFrame

from app.pipecat_pipeline.call_context import CallContext
from app.pipecat_pipeline.filler_audio import (
    FILLER_AUDIO_FILENAMES,
    create_filler_audio_player,
    filler_audio_path_for_intent,
    load_filler_audio_for_intent,
)


class FillerAudioTests(unittest.TestCase):
    def test_each_supported_intent_has_a_named_audio_asset(self) -> None:
        expected = {
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

        self.assertEqual(
            expected,
            FILLER_AUDIO_FILENAMES,
        )
        for configured in FILLER_AUDIO_FILENAMES.values():
            filenames = configured if isinstance(configured, tuple) else (configured,)
            for filename in filenames:
                self.assertTrue((filler_audio_path_for_intent("unknown").parent / filename).exists(), filename)

    def test_goodbye_does_not_have_a_filler(self) -> None:
        self.assertIsNone(filler_audio_path_for_intent("conversation.goodbye"))

    def test_unrecognized_intent_uses_neutral_filler(self) -> None:
        self.assertIn(filler_audio_path_for_intent("not.a.real.intent").name, FILLER_AUDIO_FILENAMES["unknown"])

    def test_unknown_intent_randomizes_across_neutral_filler_pool(self) -> None:
        with patch("app.pipecat_pipeline.filler_audio.random.choice", return_value="rumik-filler-unknown-3.wav") as choice:
            self.assertEqual("rumik-filler-unknown-3.wav", filler_audio_path_for_intent("unknown").name)

        choice.assert_called_once_with(FILLER_AUDIO_FILENAMES["unknown"])

    def test_runtime_asset_is_mono_24khz_pcm(self) -> None:
        audio = load_filler_audio_for_intent("payment.failed")

        self.assertIsNotNone(audio)
        self.assertEqual(24_000, audio.sample_rate)
        self.assertEqual(1, audio.num_channels)
        self.assertGreater(len(audio.pcm), 1_000)

    def test_neutral_filler_variants_are_mono_24khz_pcm(self) -> None:
        for filename in FILLER_AUDIO_FILENAMES["unknown"]:
            with self.subTest(filename=filename), patch(
                "app.pipecat_pipeline.filler_audio.random.choice",
                return_value=filename,
            ):
                audio = load_filler_audio_for_intent("unknown")

            self.assertIsNotNone(audio)
            self.assertEqual(filename, audio.filename)
            self.assertEqual(24_000, audio.sample_rate)
            self.assertEqual(1, audio.num_channels)
            self.assertGreater(len(audio.pcm), 1_000)


class FillerAudioPlayerTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_queues_whole_intent_audio_without_waiting_for_output(self) -> None:
        release_output = asyncio.Event()
        queued_frames: list[object] = []

        class SlowOutput:
            async def queue_frame(self, frame: object) -> None:
                queued_frames.append(frame)
                await release_output.wait()

        events: list[tuple[str, dict[str, object]]] = []
        player = create_filler_audio_player(
            output=SlowOutput(),
            context=CallContext(session_id="session-1234567890", call_id="call-1", persona={}),
            log_event=lambda event, **payload: events.append((event, payload)),
        )

        task = player.start("payment.failed")
        await asyncio.sleep(0)

        self.assertFalse(task.done())
        self.assertIsInstance(queued_frames[0], TTSAudioRawFrame)
        self.assertEqual(
            "rumik-filler-payment-failed.wav",
            next(payload["filename"] for event, payload in events if event == "voice_filler_started"),
        )

        release_output.set()
        await task

        self.assertIsInstance(queued_frames[1], TTSStoppedFrame)
        self.assertIn("voice_filler_queued", [event for event, _payload in events])

    async def test_start_avoids_repeating_neutral_variant_back_to_back(self) -> None:
        output = AsyncMock()
        events: list[tuple[str, dict[str, object]]] = []
        player = create_filler_audio_player(
            output=output,
            context=CallContext(session_id="session-1234567890", call_id="call-1", persona={}),
            log_event=lambda event, **payload: events.append((event, payload)),
        )

        with patch(
            "app.pipecat_pipeline.filler_audio.random.choice",
            side_effect=lambda choices: choices[0],
        ) as choice:
            await player.start("unknown")
            await player.start("unknown")

        self.assertEqual(
            [
                "rumik-filler-unknown.wav",
                "rumik-filler-unknown-2.wav",
            ],
            [payload["filename"] for event, payload in events if event == "voice_filler_started"],
        )
        self.assertEqual(FILLER_AUDIO_FILENAMES["unknown"], choice.call_args_list[0].args[0])
        self.assertNotIn("rumik-filler-unknown.wav", choice.call_args_list[1].args[0])

    async def test_start_skips_goodbye_with_a_structured_log(self) -> None:
        output = AsyncMock()
        events: list[tuple[str, dict[str, object]]] = []
        player = create_filler_audio_player(
            output=output,
            context=CallContext(session_id="session-1234567890", call_id="call-1", persona={}),
            log_event=lambda event, **payload: events.append((event, payload)),
        )

        task = player.start("conversation.goodbye")
        await task

        output.queue_frame.assert_not_awaited()
        self.assertEqual(["voice_filler_skipped"], [event for event, _payload in events])
        self.assertEqual("conversation_goodbye", events[0][1]["reason"])

    async def test_start_logs_asset_loading_failure_without_raising(self) -> None:
        output = AsyncMock()
        events: list[tuple[str, dict[str, object]]] = []
        player = create_filler_audio_player(
            output=output,
            context=CallContext(session_id="session-1234567890", call_id="call-1", persona={}),
            log_event=lambda event, **payload: events.append((event, payload)),
        )

        with patch(
            "app.pipecat_pipeline.filler_audio.load_filler_audio_from_path",
            side_effect=FileNotFoundError("missing filler"),
        ):
            await player.start("payment.failed")

        output.queue_frame.assert_not_awaited()
        self.assertEqual(["voice_filler_failed"], [event for event, _payload in events])
        self.assertEqual("missing filler", events[0][1]["error"])
