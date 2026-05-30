from __future__ import annotations

import json
import logging
import unittest

from app.domain.agent import run_stable_agent_turn


class AgentLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_logs_voice_turn_boundaries_for_fallback_answer(self) -> None:
        persona = {
            "customer_id": "CUST-1",
            "persona_id": "demo",
            "name": "Demo User",
            "mobile_last_4": "1234",
            "kyc_status": "approved",
            "payments": [],
            "fixed_deposits": [],
            "open_tickets": [],
            "secure_links": [],
        }

        with self.assertLogs("app.domain.agent", level=logging.INFO) as captured:
            await run_stable_agent_turn(
                session_id="session-123",
                persona=persona,
                transcript="hello can you hear me",
                history=[],
                call_verified=False,
                verified_mobile_last4=None,
                pending_route=None,
            )

        events = [json.loads(line.split(" ", 1)[1]) for line in captured.output]
        self.assertEqual(["agent_turn_received", "agent_turn_completed"], [event["event"] for event in events])
        self.assertEqual("hello can you hear me", events[0]["transcript"])
        self.assertEqual("unknown", events[0]["route"]["intent"])
        self.assertEqual([], events[0]["route"]["tools"])
        self.assertEqual("session-123", events[0]["session_id"])
        self.assertIn("Main help kar sakti hoon", events[1]["tts_text"])
        self.assertEqual([], events[1]["tool_calls"])


if __name__ == "__main__":
    unittest.main()
