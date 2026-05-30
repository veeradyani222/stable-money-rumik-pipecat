from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CallContext:
    session_id: str
    call_id: str
    persona: dict[str, Any]
    history: list[dict[str, str]] = field(default_factory=list)
    call_verified: bool = False
    verified_mobile_last4: str | None = None
    pending_route: dict[str, Any] | None = None
    latest_transcript: str | None = None
    latest_route: dict[str, Any] | None = None
    latest_tool_names: list[str] = field(default_factory=list)
    latest_tool_calls: list[str] = field(default_factory=list)

    def add_user_turn(self, text: str) -> None:
        self.history.append({"role": "user", "text": text})
        self.history = self.history[-32:]

    def add_model_turn(self, text: str) -> None:
        self.history.append({"role": "model", "text": text})
        self.history = self.history[-32:]
