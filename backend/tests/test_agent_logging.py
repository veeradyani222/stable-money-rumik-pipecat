from __future__ import annotations

import json
import logging
import unittest
from unittest.mock import AsyncMock, patch

from app.domain.agent import run_stable_agent_turn
from app.domain.policies import route_for_intent


class AgentLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_turn_runner_uses_ai_fallback_resolver(self) -> None:
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

        with patch(
            "app.domain.agent.resolve_stable_turn_route_ai",
            new=AsyncMock(return_value=route_for_intent("kyc.explainer")),
        ) as resolve:
            answer = await run_stable_agent_turn(
                session_id="session-123",
                persona=persona,
                transcript="tell me what customer verification means",
                history=[],
                call_verified=False,
                verified_mobile_last4=None,
                pending_route=None,
            )

        self.assertIn("Know Your Customer", answer["text"])
        resolve.assert_awaited_once_with("tell me what customer verification means", [])

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

        with patch(
            "app.domain.agent.resolve_stable_turn_route_ai",
            new=AsyncMock(return_value=route_for_intent("unknown")),
        ), self.assertLogs("app.domain.agent", level=logging.INFO) as captured:
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
