from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agent.read_access import dob_matches, verify_read_access


class ReadAccessDobTests(unittest.IsolatedAsyncioTestCase):
    def test_dob_matches_spoken_english_day_month_year(self) -> None:
        self.assertTrue(dob_matches("1993-07-30", "thirty July nineteen ninety three"))
        self.assertTrue(dob_matches("1993-07-30", "thirtieth July nineteen ninety-three"))

    async def _verify(self, ai_verdict: str) -> dict[str, object]:
        persona = {
            "customer_id": "cust-1",
            "name": "Demo",
            "mobile_last_4": "1123",
            "date_of_birth": "1993-07-30",
        }

        class Settings:
            openai_api_key = "test-key"

        async def fake_match_dob_ai(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {"verdict": ai_verdict, "model_answered": True}

        async def fake_match_mobile_ai(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {"verdict": "match", "extracted_last_four": "1123", "model_answered": True}

        with patch.dict("os.environ", {}, clear=True), patch("app.agent.read_access.get_settings", return_value=Settings()), patch(
            "app.agent.read_access.match_mobile_last_four_ai",
            side_effect=fake_match_mobile_ai,
        ), patch(
            "app.agent.read_access.match_dob_ai",
            side_effect=fake_match_dob_ai,
        ):
            return await verify_read_access(
                persona,
                {"mobile_last_4": "1123", "date_of_birth": "30 July 1993"},
                verified_mobile_last4="1123",
            )

    async def test_dob_ai_verdict_is_final_when_configured(self) -> None:
        no_match = await self._verify("no_match")
        match = await self._verify("match")

        self.assertFalse(no_match["ok"])
        self.assertTrue(match["ok"])


class ReadAccessMobileTests(unittest.IsolatedAsyncioTestCase):
    async def test_mobile_ai_verdict_is_final_when_configured_even_for_exact_digits(self) -> None:
        persona = {
            "customer_id": "cust-1",
            "name": "Demo",
            "mobile_last_4": "1123",
            "date_of_birth": "1993-07-30",
        }

        class Settings:
            openai_api_key = "test-key"

        async def fake_match_mobile_ai(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {"verdict": "no_match", "extracted_last_four": "1123", "model_answered": True}

        with patch.dict("os.environ", {}, clear=True), patch("app.agent.read_access.get_settings", return_value=Settings()), patch(
            "app.agent.read_access.match_mobile_last_four_ai",
            side_effect=fake_match_mobile_ai,
        ):
            result = await verify_read_access(persona, {"mobile_last_4": "1123"})

        self.assertFalse(result["ok"])
        self.assertEqual("mobile_last_4_required", result["data"]["verification_step"])


if __name__ == "__main__":
    unittest.main()
