from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from app.agent.intent_classifier_ai import resolve_stable_turn_route_ai
from app.domain.rumik_text import normalize_rumik_text
from app.domain.secure_links import send_secure_link_for_session
from app.domain.support_tickets import create_support_ticket_for_session
from app.domain.tools import execute_tool_with_context


AGENT_MAX_HISTORY_MESSAGES = 64
logger = logging.getLogger(__name__)


def _log_agent_event(event: str, **payload: Any) -> None:
    logger.info("%s %s", event, json.dumps({"event": event, **payload}, ensure_ascii=False, default=str))


def valid_history(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for item in value[-AGENT_MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        text = item.get("text")
        if role in {"user", "model"} and isinstance(text, str) and text.strip():
            out.append({"role": role, "text": text.strip()})
    return out


def turn_policy(route: dict[str, Any]) -> dict[str, Any]:
    return {"endCallAfterResponse": route.get("intent") == "conversation.goodbye"}


def _verification_args(transcript: str, verified_mobile_last4: str | None) -> dict[str, str]:
    if verified_mobile_last4:
        return {"mobile_last_4": verified_mobile_last4, "date_of_birth": transcript}
    return {"mobile_last_4": transcript, "date_of_birth": ""}


def _account_tool(route: dict[str, Any]) -> str | None:
    for tool in route.get("tools") or []:
        if tool != "verify_read_access":
            return tool
    return None


def _base_unknown_answer() -> str:
    return "[neutral] Main help kar sakti hoon. Payment, FD, KYC, ticket, ya support contact ke baare mein bataiye."


async def run_stable_agent_turn(
    *,
    session_id: str,
    persona: dict[str, Any],
    transcript: str,
    history: list[dict[str, str]],
    call_verified: bool,
    verified_mobile_last4: str | None,
    pending_route: dict[str, Any] | None,
    on_mobile_gate: Any | None = None,
) -> dict[str, Any]:
    route_source = "pending_route" if verified_mobile_last4 and pending_route else "router"
    route = pending_route if route_source == "pending_route" else await resolve_stable_turn_route_ai(transcript, history)
    tool_calls: list[str] = []
    verified = call_verified
    _log_agent_event(
        "agent_turn_received",
        session_id=session_id,
        transcript=transcript,
        history=history,
        route=route,
        route_source=route_source,
        context={
            "persona_id": persona.get("persona_id"),
            "customer_id": persona.get("customer_id"),
            "call_verified": call_verified,
            "has_verified_mobile_last4": bool(verified_mobile_last4),
            "has_pending_route": bool(pending_route),
            "payment_count": len(persona.get("payments") or []),
            "fd_count": len(persona.get("fixed_deposits") or []),
            "ticket_count": len(persona.get("open_tickets") or []),
            "secure_link_count": len(persona.get("secure_links") or []),
        },
    )

    def complete(answer: dict[str, Any]) -> dict[str, Any]:
        _log_agent_event(
            "agent_turn_completed",
            session_id=session_id,
            transcript=transcript,
            route=answer.get("route", route),
            tool_calls=answer.get("toolCalls", []),
            verified=answer.get("verified"),
            tts_text=answer.get("text", ""),
            end_call_after_response=answer.get("endCallAfterResponse", False),
        )
        return answer

    if route["intent"] == "conversation.goodbye":
        return complete({
            "text": "[neutral] Dhanyavaad. Main call ab end kar rahi hoon.",
            "toolCalls": [],
            "verified": verified,
            "route": route,
            **turn_policy(route),
        })

    if route["intent"] == "unknown":
        return complete({"text": _base_unknown_answer(), "toolCalls": [], "verified": verified, "route": route, **turn_policy(route)})

    needs_auth = route["authTier"] in {"Tier B", "Tier C"}
    if needs_auth and not verified:
        should_verify_now = verified_mobile_last4 or any(
            (item.get("role") == "model" and ("last four" in item.get("text", "").lower() or "date of birth" in item.get("text", "").lower()))
            for item in history[-4:]
        )
        if not should_verify_now:
            return complete({
                "text": "[neutral] Account details check karne ke liye registered mobile number ke last four digits batayein.",
                "toolCalls": [],
                "verified": False,
                "route": route,
                **turn_policy(route),
            })
        verification = await execute_tool_with_context(
            persona,
            "verify_read_access",
            _verification_args(transcript, verified_mobile_last4),
            call_verified=False,
            verified_mobile_last4=verified_mobile_last4,
        )
        tool_calls.append("verify_read_access")
        _log_agent_event(
            "agent_tool_result",
            session_id=session_id,
            tool="verify_read_access",
            ok=verification.get("ok"),
            summary=verification.get("summary"),
            data=verification.get("data"),
        )
        data = verification.get("data") or {}
        if data.get("mobile_step_verified") is True and data.get("verified") is not True and on_mobile_gate:
            await on_mobile_gate(persona["mobile_last_4"], route)
        if data.get("verified") is True:
            verified = True
            account_tool = _account_tool(route)
            if account_tool:
                tool_result = await execute_tool_with_context(
                    persona,
                    account_tool,
                    {},
                    call_verified=True,
                    verified_mobile_last4=persona["mobile_last_4"],
                    create_support_ticket=lambda args: create_support_ticket_for_session(session_id, args),
                    send_secure_link=lambda args: send_secure_link_for_session(session_id, args),
                )
                tool_calls.append(account_tool)
                _log_agent_event(
                    "agent_tool_result",
                    session_id=session_id,
                    tool=account_tool,
                    ok=tool_result.get("ok"),
                    summary=tool_result.get("summary"),
                    data=tool_result.get("data"),
                )
                text = f"{verification['summary']} {tool_result['summary']}"
                return complete({"text": normalize_rumik_text(text), "toolCalls": tool_calls, "verified": True, "route": route, **turn_policy(route)})
        return complete({"text": normalize_rumik_text(verification["summary"]), "toolCalls": tool_calls, "verified": verified, "route": route, **turn_policy(route)})

    selected_tools = [tool for tool in route.get("tools") or [] if tool != "verify_read_access"]
    if not selected_tools:
        if route["intent"] == "kyc.explainer":
            return complete({
                "text": "[neutral] KYC ka matlab Know Your Customer identity verification hota hai. Status check karne ke liye verification chahiye.",
                "toolCalls": [],
                "verified": verified,
                "route": route,
                **turn_policy(route),
            })
        return complete({"text": _base_unknown_answer(), "toolCalls": [], "verified": verified, "route": route, **turn_policy(route)})

    parts: list[str] = []
    for tool in selected_tools:
        result = await execute_tool_with_context(
            persona,
            tool,
            {},
            call_verified=verified,
            verified_mobile_last4=verified_mobile_last4,
            create_support_ticket=lambda args: create_support_ticket_for_session(session_id, args),
            send_secure_link=lambda args: send_secure_link_for_session(session_id, args),
        )
        tool_calls.append(tool)
        _log_agent_event(
            "agent_tool_result",
            session_id=session_id,
            tool=tool,
            ok=result.get("ok"),
            summary=result.get("summary"),
            data=result.get("data"),
        )
        parts.append(result["summary"])
    return complete({"text": normalize_rumik_text(" ".join(parts)), "toolCalls": tool_calls, "verified": verified, "route": route, **turn_policy(route)})


async def stream_stable_agent_events(**kwargs: Any) -> AsyncIterator[tuple[str, Any]]:
    yield "ready", {"ok": True}
    answer = await run_stable_agent_turn(**kwargs)
    route = answer.pop("route")
    yield "route", route
    yield "policy", turn_policy(route)
    yield "delta", {"delta": answer["text"]}
    yield "done", answer
    yield "close", {}
