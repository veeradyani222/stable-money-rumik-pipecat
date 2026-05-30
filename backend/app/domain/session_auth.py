from __future__ import annotations

import json
import re
from typing import Any

DEMO_SESSION_COOKIE = "stable_demo_session"

_call_verified: dict[str, bool] = {}
_call_mobile_gate: dict[str, str] = {}
_call_pending_route: dict[str, dict[str, Any]] = {}


def _session_id(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalized_call_id(call_id: Any = None) -> str:
    return call_id.strip() if isinstance(call_id, str) and call_id.strip() else "legacy"


def call_state_key(session_id: str, call_id: Any = None) -> str:
    return f"{session_id}:{normalized_call_id(call_id)}"


def last_four_digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))[-4:]


def resolve_demo_session_id(explicit_session_id: Any = None, cookie_session_id: Any = None) -> dict[str, Any]:
    explicit = _session_id(explicit_session_id)
    cookie = _session_id(cookie_session_id)
    if explicit and cookie and explicit != cookie:
        return {"ok": False, "status": 403, "error": "Session does not match this browser"}
    session_id = explicit or cookie
    if len(session_id) < 10:
        return {"ok": False, "status": 400, "error": "Missing or invalid session_id"}
    return {"ok": True, "sessionId": session_id}


def get_demo_call_verified(session_id: str, call_id: Any = None) -> bool:
    return _call_verified.get(call_state_key(session_id, call_id)) is True


def mark_demo_call_verified(session_id: str, call_id: Any = None) -> None:
    key = call_state_key(session_id, call_id)
    _call_verified[key] = True
    _call_mobile_gate.pop(key, None)
    _call_pending_route.pop(key, None)


def get_demo_call_verified_mobile_last_four(session_id: str, call_id: Any = None) -> str | None:
    return _call_mobile_gate.get(call_state_key(session_id, call_id))


def mark_demo_call_verified_mobile_last_four(session_id: str, call_id: Any, last_four: str) -> None:
    digits = last_four_digits(last_four)
    if len(digits) == 4:
        _call_mobile_gate[call_state_key(session_id, call_id)] = digits


def get_demo_call_pending_route(session_id: str, call_id: Any = None) -> dict[str, Any] | None:
    return _call_pending_route.get(call_state_key(session_id, call_id))


def mark_demo_call_pending_route(session_id: str, call_id: Any, route: dict[str, Any] | None) -> None:
    if route and route.get("intent") != "unknown":
        _call_pending_route[call_state_key(session_id, call_id)] = route


async def get_persisted_demo_call_verified(connection: Any, session_id: str, call_id: Any = None) -> bool:
    row = await connection.fetchrow(
        "SELECT 1 FROM demo_call_verifications WHERE session_id = $1 AND call_id = $2 LIMIT 1",
        session_id,
        normalized_call_id(call_id),
    )
    return row is not None


async def mark_persisted_demo_call_verified(connection: Any, session_id: str, call_id: Any = None) -> None:
    await connection.execute(
        """
        INSERT INTO demo_call_verifications (session_id, call_id)
        VALUES ($1, $2)
        ON CONFLICT (session_id, call_id)
        DO UPDATE SET verified_at = NOW()
        """,
        session_id,
        normalized_call_id(call_id),
    )


async def get_persisted_demo_call_mobile_gate(connection: Any, session_id: str, call_id: Any = None) -> tuple[str | None, dict[str, Any] | None]:
    row = await connection.fetchrow(
        """
        SELECT mobile_last_4, pending_route
        FROM demo_call_mobile_verifications
        WHERE session_id = $1 AND call_id = $2
        LIMIT 1
        """,
        session_id,
        normalized_call_id(call_id),
    )
    if not row:
        return None, None
    digits = last_four_digits(row.get("mobile_last_4"))
    raw_route = row.get("pending_route")
    if isinstance(raw_route, str):
        try:
            raw_route = json.loads(raw_route)
        except json.JSONDecodeError:
            raw_route = None
    route = raw_route if isinstance(raw_route, dict) else None
    return (digits if len(digits) == 4 else None), route


async def mark_persisted_demo_call_mobile_gate(
    connection: Any,
    session_id: str,
    call_id: Any,
    last_four: str,
    pending_route: dict[str, Any] | None = None,
) -> None:
    digits = last_four_digits(last_four)
    if len(digits) != 4:
        return
    await connection.execute(
        """
        INSERT INTO demo_call_mobile_verifications (session_id, call_id, mobile_last_4, pending_route)
        VALUES ($1, $2, $3, $4::jsonb)
        ON CONFLICT (session_id, call_id)
        DO UPDATE SET mobile_last_4 = EXCLUDED.mobile_last_4,
                      pending_route = EXCLUDED.pending_route,
                      verified_at = NOW()
        """,
        session_id,
        normalized_call_id(call_id),
        digits,
        json.dumps(pending_route) if pending_route else None,
    )


async def clear_persisted_demo_call_mobile_gate(connection: Any, session_id: str, call_id: Any = None) -> None:
    await connection.execute(
        "DELETE FROM demo_call_mobile_verifications WHERE session_id = $1 AND call_id = $2",
        session_id,
        normalized_call_id(call_id),
    )


async def get_demo_call_verified_from_store(connection: Any, session_id: str, call_id: Any = None) -> bool:
    try:
        return await get_persisted_demo_call_verified(connection, session_id, call_id)
    except Exception:
        return get_demo_call_verified(session_id, call_id)


async def mark_demo_call_verified_in_store(connection: Any, session_id: str, call_id: Any = None) -> None:
    mark_demo_call_verified(session_id, call_id)
    try:
        await mark_persisted_demo_call_verified(connection, session_id, call_id)
        await clear_persisted_demo_call_mobile_gate(connection, session_id, call_id)
    except Exception:
        pass


async def get_demo_call_mobile_state_from_store(connection: Any, session_id: str, call_id: Any = None) -> tuple[str | None, dict[str, Any] | None]:
    try:
        mobile, route = await get_persisted_demo_call_mobile_gate(connection, session_id, call_id)
        return mobile or get_demo_call_verified_mobile_last_four(session_id, call_id), route or get_demo_call_pending_route(session_id, call_id)
    except Exception:
        return get_demo_call_verified_mobile_last_four(session_id, call_id), get_demo_call_pending_route(session_id, call_id)


async def mark_demo_call_mobile_gate_in_store(
    connection: Any,
    session_id: str,
    call_id: Any,
    last_four: str,
    pending_route: dict[str, Any] | None = None,
) -> None:
    mark_demo_call_verified_mobile_last_four(session_id, call_id, last_four)
    mark_demo_call_pending_route(session_id, call_id, pending_route)
    try:
        await mark_persisted_demo_call_mobile_gate(connection, session_id, call_id, last_four, pending_route)
    except Exception:
        pass
