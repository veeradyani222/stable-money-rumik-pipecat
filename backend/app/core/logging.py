from __future__ import annotations

import logging
import os

from loguru import logger as loguru_logger

PIPECAT_PROMPT_DUMP_LOGGERS = (
    "pipecat.services.llm_service",
    "pipecat.services.openai.responses.llm",
)


def configure_runtime_logging(*, debug_all: bool | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
    )
    logging.getLogger("app").setLevel(logging.INFO)

    show_all_debug = debug_all if debug_all is not None else os.getenv("DEBUG_LOG_ALL", "").lower() in {"1", "true", "yes", "on"}
    if show_all_debug:
        return
    for logger_name in PIPECAT_PROMPT_DUMP_LOGGERS:
        loguru_logger.disable(logger_name)
