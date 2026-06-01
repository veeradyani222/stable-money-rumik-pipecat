from __future__ import annotations

from app.core.logging import configure_runtime_logging

configure_runtime_logging()

from app.pipecat_pipeline.bot import bot

__all__ = ["bot"]
