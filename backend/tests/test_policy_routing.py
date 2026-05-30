from __future__ import annotations

import unittest

from app.domain.policies import route_stable_turn, trace_stable_turn_route


class PolicyRoutingTests(unittest.TestCase):
    def test_backend_routes_frontend_payment_summary_keywords(self) -> None:
        for transcript in ("mere pe", "पेमेंट हिस्ट्री", "پیمنٹس کے بارے"):
            with self.subTest(transcript=transcript):
                self.assertEqual("payment.summary", route_stable_turn(transcript)["intent"])

    def test_backend_routes_frontend_multilingual_keywords(self) -> None:
        cases = {
            "एफडी बुक": "fd.book.status",
            "ಕೆವೈಸಿ ಸ್ಥಿತಿ": "kyc.status",
            "રિફંડ ક્યારે": "refund.status",
            "મોબાઇલ નંબર બદલ": "secure.action.help",
            "बस हो गया": "conversation.goodbye",
        }
        for transcript, intent in cases.items():
            with self.subTest(transcript=transcript):
                self.assertEqual(intent, route_stable_turn(transcript)["intent"])

    def test_backend_trace_reports_keyword_and_history_source(self) -> None:
        keyword_trace = trace_stable_turn_route("stable money safe")
        history_trace = trace_stable_turn_route("haan", [{"role": "user", "text": "refund kab milega"}])

        self.assertEqual("keyword", keyword_trace["matchSource"])
        self.assertEqual("app.real.check", keyword_trace["route"]["intent"])
        self.assertEqual("history", history_trace["matchSource"])
        self.assertEqual("refund.status", history_trace["route"]["intent"])


if __name__ == "__main__":
    unittest.main()
