from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.config import get_settings


class ConfigTests(unittest.TestCase):
    def test_intent_model_defaults_to_gpt_5_mini_for_verification(self) -> None:
        with patch.dict("os.environ", {"OPENAI_AGENT_MODEL": "gpt-4o-mini"}, clear=True):
            self.assertEqual("gpt-5-mini", get_settings().openai_intent_model)


if __name__ == "__main__":
    unittest.main()
