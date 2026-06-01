from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.config import get_settings


class ConfigTests(unittest.TestCase):
    def test_intent_model_defaults_to_gpt_4_1_mini_for_verification(self) -> None:
        with patch("app.core.config.load_project_env"), patch.dict(
            "os.environ",
            {"OPENAI_AGENT_MODEL": "gpt-4o-mini"},
            clear=True,
        ):
            self.assertEqual("gpt-4.1-mini", get_settings().openai_intent_model)

    def test_filler_audio_defaults_to_disabled(self) -> None:
        with patch("app.core.config.load_project_env"), patch.dict("os.environ", {}, clear=True):
            self.assertFalse(get_settings().enable_filler_audio)

    def test_filler_audio_accepts_explicit_true_values(self) -> None:
        for value in ("true", "TRUE", " 1 ", "yes", "on"):
            with self.subTest(value=value), patch("app.core.config.load_project_env"), patch.dict(
                "os.environ",
                {"ENABLE_FILLER_AUDIO": value},
                clear=True,
            ):
                self.assertTrue(get_settings().enable_filler_audio)

    def test_filler_audio_rejects_false_like_values(self) -> None:
        for value in ("", "false", "0", "no", "off", "anything-else"):
            with self.subTest(value=value), patch("app.core.config.load_project_env"), patch.dict(
                "os.environ",
                {"ENABLE_FILLER_AUDIO": value},
                clear=True,
            ):
                self.assertFalse(get_settings().enable_filler_audio)


if __name__ == "__main__":
    unittest.main()
