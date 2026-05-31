from __future__ import annotations

import io
import logging
import unittest
from unittest.mock import patch

from app.core.logging import PIPECAT_PROMPT_DUMP_LOGGERS, configure_runtime_logging


class LoggingConfigTests(unittest.TestCase):
    def test_runtime_logging_suppresses_pipecat_prompt_dump_modules_by_default(self) -> None:
        with patch("app.core.logging.loguru_logger") as logger:
            configure_runtime_logging(debug_all=False)

        self.assertEqual(
            list(PIPECAT_PROMPT_DUMP_LOGGERS),
            [call.args[0] for call in logger.disable.call_args_list],
        )

    def test_runtime_logging_keeps_pipecat_debug_when_explicitly_enabled(self) -> None:
        with patch("app.core.logging.loguru_logger") as logger:
            configure_runtime_logging(debug_all=True)

        logger.disable.assert_not_called()

    def test_runtime_logging_surfaces_app_info_logs_to_console(self) -> None:
        root_logger = logging.getLogger()
        previous_handlers = list(root_logger.handlers)
        previous_level = root_logger.level
        previous_app_level = logging.getLogger("app").level
        stream = io.StringIO()

        try:
            for handler in previous_handlers:
                root_logger.removeHandler(handler)
            with patch("sys.stderr", stream):
                configure_runtime_logging(debug_all=False)
                logging.getLogger("app.pipecat_pipeline.bot").info(
                    "voice_transcript_received %s",
                    '{"event":"voice_transcript_received","transcript":"hello"}',
                )
        finally:
            for handler in list(root_logger.handlers):
                root_logger.removeHandler(handler)
                handler.close()
            for handler in previous_handlers:
                root_logger.addHandler(handler)
            root_logger.setLevel(previous_level)
            logging.getLogger("app").setLevel(previous_app_level)

        output = stream.getvalue()
        self.assertIn("voice_transcript_received", output)
        self.assertIn('"transcript":"hello"', output)


if __name__ == "__main__":
    unittest.main()
