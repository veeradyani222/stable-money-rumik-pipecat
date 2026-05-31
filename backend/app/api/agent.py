from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Cookie, HTTPException, Request

from app.db.pool import acquire
from app.domain.personas import build_persona_brief, build_persona_from_row
from app.domain.policies import get_persona_suggestions
from app.domain.session_auth import (
    DEMO_SESSION_COOKIE,
    resolve_demo_session_id,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])

PERSONA_SELECT_SQL = """
SELECT email, persona_id, customer_id, name, mobile_last_4, date_of_birth::text AS date_of_birth,
       kyc_status, kyc_rejection_reason, kyc_eta, kyc_next_step,
       payments, fixed_deposits, open_tickets, secure_links
FROM demo_users
WHERE session_id = $1
LIMIT 1
"""


def _http_session_result(explicit: Any, cookie: str | None) -> dict[str, Any]:
    result = resolve_demo_session_id(explicit, cookie)
    if not result["ok"]:
        raise HTTPException(status_code=result["status"], detail=result["error"])
    return result


@router.get("/session")
async def agent_session(request: Request, stable_demo_session: str | None = Cookie(default=None, alias=DEMO_SESSION_COOKIE)):
    session_result = _http_session_result(request.query_params.get("session_id"), stable_demo_session)
    session_id = session_result["sessionId"]
    async with acquire() as connection:
        row = await connection.fetchrow(PERSONA_SELECT_SQL, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    data = dict(row)
    if not data.get("persona_id"):
        raise HTTPException(status_code=409, detail="Persona not selected yet")
    persona = build_persona_from_row(data)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona is not available in this build")
    return {
        "session_id": session_id,
        "email": data["email"],
        "persona": persona,
        "brief": build_persona_brief(persona),
        "suggestions": get_persona_suggestions(persona),
    }
