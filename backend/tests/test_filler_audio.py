from __future__ import annotations

import unittest

from app.pipecat_pipeline.filler_audio import (
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
            "unknown": "rumik-filler-unknown.wav",
        }

        self.assertEqual(
            expected,
            {intent: filler_audio_path_for_intent(intent).name for intent in expected},
        )

    def test_goodbye_does_not_have_a_filler(self) -> None:
        self.assertIsNone(filler_audio_path_for_intent("conversation.goodbye"))

    def test_unrecognized_intent_uses_neutral_filler(self) -> None:
        self.assertEqual(
            "rumik-filler-unknown.wav",
            filler_audio_path_for_intent("not.a.real.intent").name,
        )

    def test_runtime_asset_is_mono_24khz_pcm(self) -> None:
        audio = load_filler_audio_for_intent("payment.failed")

        self.assertIsNotNone(audio)
        self.assertEqual(24_000, audio.sample_rate)
        self.assertEqual(1, audio.num_channels)
        self.assertGreater(len(audio.pcm), 1_000)

