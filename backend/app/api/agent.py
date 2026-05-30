from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.db.pool import acquire
from app.domain.agent import run_stable_agent_turn, stream_stable_agent_events, valid_history
from app.domain.personas import build_persona_brief, build_persona_from_row
from app.domain.policies import get_persona_suggestions
from app.domain.session_auth import (
    DEMO_SESSION_COOKIE,
    get_demo_call_mobile_state_from_store,
    get_demo_call_verified_from_store,
    mark_demo_call_mobile_gate_in_store,
    mark_demo_call_verified_in_store,
    resolve_demo_session_id,
)
from app.sse import encode_event

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


async def _load_turn_context(body: dict[str, Any], cookie_session: str | None) -> dict[str, Any]:
    session_result = _http_session_result(body.get("session_id"), cookie_session)
    session_id = session_result["sessionId"]
    transcript = body.get("transcript")
    if not isinstance(transcript, str) or len(transcript.strip()) < 2:
        raise HTTPException(status_code=400, detail="Transcript is too short")
    async with acquire() as connection:
        row = await connection.fetchrow(PERSONA_SELECT_SQL, session_id)
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        persona = build_persona_from_row(dict(row))
        if not persona:
            raise HTTPException(status_code=409, detail="Persona not selected")
        call_id = body.get("call_id")
        verified = await get_demo_call_verified_from_store(connection, session_id, call_id)
        mobile_gate, pending_route = await get_demo_call_mobile_state_from_store(connection, session_id, call_id)
    return {
        "session_id": session_id,
        "call_id": body.get("call_id"),
        "persona": persona,
        "transcript": transcript.strip(),
        "history": valid_history(body.get("history")),
        "call_verified": verified,
        "verified_mobile_last4": mobile_gate,
        "pending_route": pending_route,
    }


@router.post("/respond")
async def respond(body: dict[str, Any], stable_demo_session: str | None = Cookie(default=None, alias=DEMO_SESSION_COOKIE)):
    context = await _load_turn_context(body, stable_demo_session)
    async def on_mobile_gate(last_four: str, route: dict[str, Any]) -> None:
        async with acquire() as connection:
            await mark_demo_call_mobile_gate_in_store(connection, context["session_id"], context["call_id"], last_four, route)

    answer = await run_stable_agent_turn(**context, on_mobile_gate=on_mobile_gate)
    if answer.get("verified"):
        async with acquire() as connection:
            await mark_demo_call_verified_in_store(connection, context["session_id"], context["call_id"])
    answer.pop("route", None)
    return answer


@router.post("/respond-stream")
async def respond_stream(body: dict[str, Any], stable_demo_session: str | None = Cookie(default=None, alias=DEMO_SESSION_COOKIE)):
    context = await _load_turn_context(body, stable_demo_session)

    async def on_mobile_gate(last_four: str, route: dict[str, Any]) -> None:
        async with acquire() as connection:
            await mark_demo_call_mobile_gate_in_store(connection, context["session_id"], context["call_id"], last_four, route)

    async def generator():
        done_payload: dict[str, Any] | None = None
        async for event, data in stream_stable_agent_events(**context, on_mobile_gate=on_mobile_gate):
            if event == "done":
                done_payload = data
            yield encode_event(event, data)
        if done_payload and done_payload.get("verified"):
            async with acquire() as connection:
                await mark_demo_call_verified_in_store(connection, context["session_id"], context["call_id"])

    return StreamingResponse(generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive"})

