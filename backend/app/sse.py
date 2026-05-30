from __future__ import annotations

import json
from typing import Any


def encode_event(event: str, data: Any) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode("utf-8")

