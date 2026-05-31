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

    def test_urdu_fd_amount_followup_routes_to_fd_summary(self) -> None:
        self.assertEqual(
            "fd.summary",
            route_stable_turn("اچھا میری ٹوٹل دو ایف ڈی ہیں تو دونوں میں اماؤنٹ کتنا کتنا ہے؟")["intent"],
        )

    def test_hindi_fd_summary_without_nukta_routes_to_fd_summary(self) -> None:
        self.assertEqual(
            "fd.summary",
            route_stable_turn(
                "\u0924\u094b \u092f\u0947 \u0938\u092c\u0938\u0947 \u092a\u0939\u0932\u0947 "
                "\u092e\u0941\u091d\u0947 \u092e\u0947\u0930\u0940 \u090f\u092b\u0921\u0940\u091c "
                "\u0915\u0947 \u092c\u093e\u0930\u0947 \u092e\u0947\u0902 \u091c\u093e\u0928\u0928\u093e "
                "\u0939\u0948\u0964"
            )["intent"],
        )

    def test_backend_trace_reports_keyword_and_history_source(self) -> None:
        keyword_trace = trace_stable_turn_route("stable money safe")
        history_trace = trace_stable_turn_route("haan", [{"role": "user", "text": "refund kab milega"}])

        self.assertEqual("keyword", keyword_trace["matchSource"])
        self.assertEqual("app.real.check", keyword_trace["route"]["intent"])
        self.assertEqual("history", history_trace["matchSource"])
        self.assertEqual("refund.status", history_trace["route"]["intent"])


if __name__ == "__main__":
    unittest.main()
