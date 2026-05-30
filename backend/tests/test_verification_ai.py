from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agent import dob_verification_ai, mobile_verification_ai


class VerificationAiModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_mobile_and_dob_verification_use_dedicated_model_settings(self) -> None:
        captured_models: list[str] = []
        captured_bodies: list[dict[str, object]] = []

        class Settings:
            openai_api_key = "test-key"
            openai_agent_model = "gpt-4o-mini"
            openai_intent_model = "gpt-5-mini"

        async def fake_post(_api_key: str, body: dict[str, object]) -> dict[str, object]:
            captured_bodies.append(body)
            captured_models.append(str(body["model"]))
            if "mobile" in str(body.get("instructions")):
                return {"output_text": '{"verdict":"match","extracted_last_four":"1123","reason":"ok"}'}
            return {"output_text": '{"verdict":"match","reason":"ok"}'}

        with patch.dict(
            "os.environ",
            {
                "OPENAI_MOBILE_VERIFICATION_MODEL": "gpt-5-mini-mobile",
                "OPENAI_DOB_VERIFICATION_MODEL": "gpt-5-mini-dob",
            },
        ), patch.object(mobile_verification_ai, "get_settings", return_value=Settings()), patch.object(
            dob_verification_ai,
            "get_settings",
            return_value=Settings(),
        ), patch.object(
            mobile_verification_ai,
            "_post_responses",
            side_effect=fake_post,
        ), patch.object(
            dob_verification_ai,
            "_post_responses",
            side_effect=fake_post,
        ):
            await mobile_verification_ai.match_mobile_last_four_ai("ek ek do teen", "1123", api_key="test-key")
            await dob_verification_ai.match_dob_ai("thirty July nineteen ninety three", "1993-07-30", api_key="test-key")

        self.assertEqual(["gpt-5-mini-mobile", "gpt-5-mini-dob"], captured_models)
        self.assertEqual("stable-mobile-last4-verification-v1", captured_bodies[0]["prompt_cache_key"])
        self.assertEqual("stable-dob-verification-v2", captured_bodies[1]["prompt_cache_key"])
        self.assertIn("ANY language", str(captured_bodies[0]["instructions"]))
        self.assertIn("India the date convention is dd/mm/yyyy", str(captured_bodies[1]["instructions"]))


if __name__ == "__main__":
    unittest.main()
