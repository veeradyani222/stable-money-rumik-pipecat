from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException


router = APIRouter(prefix="/api/voice", tags=["voice"])
logger = logging.getLogger(__name__)


@router.post("/timing-log")
async def timing_log(body: dict[str, Any]):
    event = body.get("event")
    if not isinstance(event, str) or not event.strip():
        raise HTTPException(status_code=400, detail="Invalid timing event")
    payload = {**body, "event": event}
    logger.info("%s %s", event, json.dumps(payload, ensure_ascii=False, default=str))
    return {"ok": True}
