from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VoicePipelineEvent = dict[str, Any]


@dataclass
class EventSink:
    events: list[VoicePipelineEvent] = field(default_factory=list)

    async def emit(self, event_type: str, **payload: Any) -> None:
        self.events.append({"type": event_type, **payload})

