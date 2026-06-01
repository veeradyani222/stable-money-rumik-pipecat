from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.agent.intent_classifier_ai import classify_intent_ai, resolve_stable_turn_route_ai


class IntentClassifierAiTests(unittest.IsolatedAsyncioTestCase):
    async def test_classifier_logs_api_request_elapsed_time(self) -> None:
        class Settings:
            openai_api_key = "test-key"
            openai_intent_model = "gpt-4.1-mini"
            openai_agent_model = "gpt-4o-mini"

        with patch("app.agent.intent_classifier_ai.get_settings", return_value=Settings()), patch(
            "app.agent.intent_classifier_ai._post_responses",
            new=AsyncMock(return_value={"output_text": '{"intent":"fd.summary"}'}),
        ), patch(
            "app.agent.intent_classifier_ai.time.monotonic",
            side_effect=[100.0, 100.456],
        ), self.assertLogs("app.agent.intent_classifier_ai", level="INFO") as logs:
            result = await classify_intent_ai("show all my deposits", [])

        self.assertEqual({"intent": "fd.summary", "model_answered": True}, result)
        self.assertIn("intent_classifier_started model=gpt-4.1-mini", logs.output[0])
        self.assertIn(
            "intent_classifier_completed model=gpt-4.1-mini elapsed_s=0.456 response_received=True",
            logs.output[1],
        )

    async def test_classifier_request_asks_for_intent_only_without_reasoning(self) -> None:
        captured_bodies: list[dict[str, object]] = []

        class Settings:
            openai_api_key = "test-key"
            openai_intent_model = "gpt-4.1-mini"
            openai_agent_model = "gpt-4o-mini"

        async def fake_post(_api_key: str, body: dict[str, object]) -> dict[str, object]:
            captured_bodies.append(body)
            return {"output_text": '{"intent":"fd.summary"}'}

        with patch("app.agent.intent_classifier_ai.get_settings", return_value=Settings()), patch(
            "app.agent.intent_classifier_ai._post_responses",
            side_effect=fake_post,
        ):
            result = await classify_intent_ai("show all my deposits", [])

        self.assertEqual({"intent": "fd.summary", "model_answered": True}, result)
        body = captured_bodies[0]
        self.assertEqual("gpt-4.1-mini", body["model"])
        self.assertNotIn("reasoning", body)
        self.assertEqual(1024, body["max_output_tokens"])
        self.assertIn("Do not include explanations or reasoning", str(body["instructions"]))
        schema = body["text"]["format"]["schema"]  # type: ignore[index]
        self.assertEqual(["intent"], list(schema["properties"]))  # type: ignore[index]
        self.assertEqual(["intent"], schema["required"])  # type: ignore[index]

    async def test_classifier_logs_incomplete_response_without_json_output(self) -> None:
        class Settings:
            openai_api_key = "test-key"
            openai_intent_model = "gpt-4.1-mini"
            openai_agent_model = "gpt-4o-mini"

        with patch("app.agent.intent_classifier_ai.get_settings", return_value=Settings()), patch(
            "app.agent.intent_classifier_ai._post_responses",
            new=AsyncMock(
                return_value={
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "output": [{"type": "reasoning", "summary": []}],
                }
            ),
        ), self.assertLogs("app.agent.intent_classifier_ai", level="WARNING") as logs:
            result = await classify_intent_ai("show all my deposits", [])

        self.assertEqual({"intent": "unknown", "model_answered": False}, result)
        self.assertIn("intent_classifier_unparseable_response", logs.output[0])
        self.assertIn("max_output_tokens", logs.output[0])

    async def test_resolver_keeps_deterministic_hit_without_calling_ai(self) -> None:
        with patch("app.agent.intent_classifier_ai.classify_intent_ai", new=AsyncMock()) as classify:
            route = await resolve_stable_turn_route_ai("refund kab milega", [])

        self.assertEqual("refund.status", route["intent"])
        classify.assert_not_awaited()

    async def test_resolver_uses_ai_only_after_deterministic_miss(self) -> None:
        with patch(
            "app.agent.intent_classifier_ai.classify_intent_ai",
            new=AsyncMock(return_value={"intent": "fd.summary", "model_answered": True}),
        ) as classify:
            route = await resolve_stable_turn_route_ai("show all my deposits", [])

        self.assertEqual("fd.summary", route["intent"])
        classify.assert_awaited_once_with("show all my deposits", [])


if __name__ == "__main__":
    unittest.main()
