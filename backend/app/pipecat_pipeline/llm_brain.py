from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from app.agent.intent_classifier_ai import resolve_stable_turn_route_ai
from app.db.pool import acquire
from app.domain.secure_links import send_secure_link_for_session
from app.domain.session_auth import mark_demo_call_mobile_gate_in_store, mark_demo_call_verified_in_store
from app.domain.stable_llm_policy import (
    ALL_STABLE_TOOL_NAMES,
    build_stable_agent_instructions,
    select_tool_names_for_request,
    stable_tool_declarations,
    stable_tool_declarations_by_name,
)
from app.domain.support_tickets import create_support_ticket_for_session
from app.domain.tools import canonical_tool_name, execute_tool_with_context
from app.pipecat_pipeline.call_context import CallContext

logger = logging.getLogger(__name__)

VoiceLogEvent = Callable[[str], None]
StructuredLogEvent = Callable[..., None]

ARGLESS_MODEL_TOOLS = {
    "lookup_customer_profile",
    "get_fd_booking_status",
    "get_payment_reconciliation_status",
    "get_kyc_status",
    "get_premature_withdrawal_quote",
    "get_support_ticket_status",
    "get_payment_summary",
    "get_fd_summary",
    "get_refund_status",
}

_SHORT_DATE_FRAGMENT = re.compile(
    r"^\s*(?:\d{1,2}|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|"
    r"nineteenth|twentieth|twenty|twenty\s+\w+|thirtieth|thirty|thirty\s+\w+)[\s.]*$",
    re.I,
)


def _is_short_verification_fragment(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if _SHORT_DATE_FRAGMENT.match(stripped):
        return True
    return len(stripped.split()) <= 4 and len(stripped) <= 40


def _log_llm_event(event: str, **payload: Any) -> None:
    logger.info("%s %s", event, json.dumps({"event": event, **payload}, ensure_ascii=False, default=str))


def build_pipecat_tools_schema(tool_names: list[str]):
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema

    schemas = []
    for tool_name in tool_names:
        declaration = stable_tool_declarations_by_name.get(tool_name)
        if not declaration:
            continue
        properties = {
            name: {"type": "string", "description": parameter.description}
            for name, parameter in declaration.parameters.items()
        }
        required = [name for name, parameter in declaration.parameters.items() if not parameter.optional]
        schemas.append(
            FunctionSchema(
                name=declaration.name,
                description=declaration.description,
                properties=properties,
                required=required,
            )
        )
    return ToolsSchema(schemas)


def initial_stable_instructions(context: CallContext) -> str:
    route = context.pending_route or {"intent": "unknown", "authTier": "Tier A", "tools": []}
    return build_stable_agent_instructions(
        route=route,
        tool_names=[],
        call_verified=context.call_verified,
        verified_mobile_last4=context.verified_mobile_last4,
    )


async def resolve_voice_route(context: CallContext, transcript: str) -> tuple[dict[str, Any], str]:
    if context.verified_mobile_last4 and context.pending_route:
        return context.pending_route, "pending_route"
    return await resolve_stable_turn_route_ai(transcript, context.history), "router"


def select_voice_tool_names(
    *,
    route: dict[str, Any],
    context: CallContext,
    transcript: str,
) -> tuple[list[str], str]:
    tool_names = select_tool_names_for_request(
        route=route,
        call_verified=context.call_verified,
        verified_mobile_last4=context.verified_mobile_last4,
        transcript=transcript,
        history=context.history,
    )
    route_tools = [
        tool
        for tool in (route.get("tools") or [])
        if tool in stable_tool_declarations_by_name and tool not in tool_names
    ]
    if "verify_read_access" in tool_names and route_tools:
        return [*tool_names, *route_tools], "route_policy_verify_then_account"
    if route.get("intent") == "unknown" and not tool_names:
        return list(ALL_STABLE_TOOL_NAMES), "broad_unknown_llm_scope"
    return tool_names, "route_policy"


def build_turn_instructions(
    *,
    route: dict[str, Any],
    tool_names: list[str],
    context: CallContext,
) -> str:
    return build_stable_agent_instructions(
        route=route,
        tool_names=tool_names,
        call_verified=context.call_verified,
        verified_mobile_last4=context.verified_mobile_last4,
    )


def _verification_utterance_with_recent_user_context(
    latest_transcript: str,
    history: list[dict[str, str]],
    *,
    max_previous_user_turns: int,
) -> str:
    latest = latest_transcript.strip()
    previous_parts: list[str] = []
    for item in reversed(history):
        if item.get("role") != "user":
            continue
        text = (item.get("text") or "").strip()
        if not text or text == latest:
            continue
        if _is_short_verification_fragment(text):
            previous_parts.append(text)
            if len(previous_parts) >= max_previous_user_turns:
                break
            continue
        break
    parts = [*reversed(previous_parts), latest]
    return " ".join(part.strip() for part in parts if part.strip()).strip()


def normalize_tool_args_for_execution(
    tool_name: str,
    raw_args: dict[str, Any] | None,
    *,
    latest_transcript: str | None,
    history: list[dict[str, str]] | None = None,
    verified_mobile_last4: str | None,
) -> dict[str, Any]:
    canonical = canonical_tool_name(tool_name)
    raw = dict(raw_args or {})
    transcript = (latest_transcript or "").strip()

    if canonical == "verify_read_access":
        mobile_arg = str(raw.get("mobile_last_4") or "").strip()
        dob_arg = str(raw.get("date_of_birth") or "").strip()
        verified_mobile = (verified_mobile_last4 or "").strip()

        if len(verified_mobile) == 4:
            raw["mobile_last_4"] = verified_mobile
            if not dob_arg and transcript and transcript != verified_mobile:
                raw["date_of_birth"] = _verification_utterance_with_recent_user_context(
                    transcript,
                    history or [],
                    max_previous_user_turns=2,
                )
            return raw

        if not re.fullmatch(r"\d{4}", mobile_arg) and transcript:
            raw["mobile_last_4"] = _verification_utterance_with_recent_user_context(
                transcript,
                history or [],
                max_previous_user_turns=2,
            )
        raw["date_of_birth"] = ""
        return raw

    if canonical in ARGLESS_MODEL_TOOLS:
        return {}

    return raw


def _route_log_payload(route: dict[str, Any] | None) -> dict[str, Any] | None:
    if not route:
        return None
    return {
        "intent": route.get("intent"),
        "authTier": route.get("authTier"),
        "tools": route.get("tools") or [],
    }


def _post_verification_tool_name(context: CallContext) -> str | None:
    route_tools = [
        canonical_tool_name(tool)
        for tool in (context.latest_route or {}).get("tools", [])
        if canonical_tool_name(tool) != "verify_read_access"
    ]
    allowed_tools = {canonical_tool_name(tool) for tool in context.latest_tool_names}
    for tool in route_tools:
        if tool in allowed_tools:
            return tool
    return route_tools[0] if route_tools else None


async def _persist_mobile_gate(context: CallContext, last_four: str, route: dict[str, Any] | None) -> None:
    context.verified_mobile_last4 = last_four
    context.pending_route = route
    async with acquire() as db:
        await mark_demo_call_mobile_gate_in_store(db, context.session_id, context.call_id, last_four, route)


async def _persist_verified_call(context: CallContext) -> None:
    context.call_verified = True
    context.verified_mobile_last4 = context.persona.get("mobile_last_4")
    context.pending_route = None
    async with acquire() as db:
        await mark_demo_call_verified_in_store(db, context.session_id, context.call_id)


def register_stable_tool_handlers(
    llm: Any,
    context: CallContext,
    *,
    log_event: StructuredLogEvent | None = None,
) -> None:
    log_event = log_event or _log_llm_event

    def make_handler(tool_name: str):
        async def handler(params: Any) -> None:
            raw_args = dict(getattr(params, "arguments", {}) or {})
            normalized_args = normalize_tool_args_for_execution(
                tool_name,
                raw_args,
                latest_transcript=context.latest_transcript,
                history=context.history,
                verified_mobile_last4=context.verified_mobile_last4,
            )
            canonical = canonical_tool_name(tool_name)
            try:
                if canonical == "send_secure_link" and not context.call_verified:
                    result = {
                        "ok": False,
                        "summary": "[neutral] Is secure action ke liye pehle read access verification zaroori hai.",
                        "data": {
                            "auth_required": True,
                            "required_tool": "verify_read_access",
                            "auth_tier": "Tier C",
                        },
                    }
                else:
                    result = await execute_tool_with_context(
                        context.persona,
                        canonical,
                        normalized_args,
                        call_verified=context.call_verified,
                        verified_mobile_last4=context.verified_mobile_last4,
                        create_support_ticket=lambda args: create_support_ticket_for_session(context.session_id, args),
                        send_secure_link=lambda args: send_secure_link_for_session(context.session_id, args),
                    )
            except Exception as exc:
                result = {
                    "ok": False,
                    "summary": "[neutral] Abhi yeh detail nahi nikal pa rahi. Main ticket create kar sakti hoon.",
                    "data": {"error": str(exc), "tool": canonical},
                }

            data = result.get("data") if isinstance(result, dict) else {}
            if canonical == "verify_read_access" and isinstance(data, dict):
                if data.get("mobile_step_verified") is True and data.get("verified") is not True:
                    last_four = str(context.persona.get("mobile_last_4") or "")
                    await _persist_mobile_gate(context, last_four, context.latest_route)
                if data.get("verified") is True:
                    await _persist_verified_call(context)

            context.latest_tool_calls.append(canonical)
            log_event(
                "voice_tool_result",
                session_id=context.session_id,
                call_id=context.call_id,
                tool=canonical,
                raw_arguments=raw_args,
                normalized_arguments=normalized_args,
                ok=result.get("ok") if isinstance(result, dict) else None,
                summary=result.get("summary") if isinstance(result, dict) else None,
                data=data,
                route=_route_log_payload(context.latest_route),
                call_verified=context.call_verified,
                verified_mobile_last4=context.verified_mobile_last4,
            )

            if canonical == "verify_read_access" and isinstance(data, dict) and data.get("verified") is True:
                post_tool = _post_verification_tool_name(context)
                if post_tool:
                    post_result = await execute_tool_with_context(
                        context.persona,
                        post_tool,
                        {},
                        call_verified=context.call_verified,
                        verified_mobile_last4=context.verified_mobile_last4,
                        create_support_ticket=lambda args: create_support_ticket_for_session(context.session_id, args),
                        send_secure_link=lambda args: send_secure_link_for_session(context.session_id, args),
                    )
                    context.latest_tool_calls.append(post_tool)
                    post_data = post_result.get("data") if isinstance(post_result, dict) else {}
                    log_event(
                        "voice_tool_result",
                        session_id=context.session_id,
                        call_id=context.call_id,
                        tool=post_tool,
                        raw_arguments={},
                        normalized_arguments={},
                        ok=post_result.get("ok") if isinstance(post_result, dict) else None,
                        summary=post_result.get("summary") if isinstance(post_result, dict) else None,
                        data=post_data,
                        route=_route_log_payload(context.latest_route),
                        call_verified=context.call_verified,
                        verified_mobile_last4=context.verified_mobile_last4,
                    )
                    if isinstance(result, dict) and isinstance(post_result, dict):
                        merged_data = dict(data)
                        merged_data["post_verification_tool"] = post_tool
                        merged_data["post_verification_result"] = post_data
                        result["data"] = merged_data
                        result["summary"] = f"{result.get('summary', '')} {post_result.get('summary', '')}".strip()
            await params.result_callback(result)

        return handler

    for declaration in stable_tool_declarations:
        llm.register_function(declaration.name, make_handler(declaration.name))


def create_stable_turn_context_processor(context: CallContext, settings_class: type[Any], *, log_event: StructuredLogEvent):
    from pipecat.frames.frames import LLMSetToolsFrame, LLMUpdateSettingsFrame, TranscriptionFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class StableTurnContextProcessor(FrameProcessor):
        async def process_frame(self, frame: Any, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if not isinstance(frame, TranscriptionFrame) or not getattr(frame, "text", "").strip():
                await self.push_frame(frame, direction)
                return

            transcript = frame.text.strip()
            route, route_source = await resolve_voice_route(context, transcript)
            tool_names, tool_scope = select_voice_tool_names(route=route, context=context, transcript=transcript)
            instructions = build_turn_instructions(route=route, tool_names=tool_names, context=context)
            context.latest_transcript = transcript
            context.latest_route = route
            context.latest_tool_names = tool_names
            context.latest_tool_calls = []

            log_event(
                "voice_transcript_received",
                session_id=context.session_id,
                call_id=context.call_id,
                transcript=transcript,
                route=route,
                route_source=route_source,
                selected_tools=tool_names,
                tool_scope=tool_scope,
                call_verified=context.call_verified,
                verified_mobile_last4=context.verified_mobile_last4,
                pending_route=context.pending_route,
            )

            await self.push_frame(LLMSetToolsFrame(build_pipecat_tools_schema(tool_names)), FrameDirection.DOWNSTREAM)
            await self.push_frame(
                LLMUpdateSettingsFrame(delta=settings_class(system_instruction=instructions)),
                FrameDirection.DOWNSTREAM,
            )
            await self.push_frame(frame, direction)

    return StableTurnContextProcessor(name="stable_turn_context")


def create_stable_llm_response_logger(context: CallContext, *, log_event: StructuredLogEvent):
    from pipecat.frames.frames import LLMFullResponseEndFrame, LLMFullResponseStartFrame, LLMTextFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class StableLlmResponseLogger(FrameProcessor):
        def __init__(self) -> None:
            super().__init__(name="stable_llm_response_logger")
            self._text_parts: list[str] = []

        async def process_frame(self, frame: Any, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if isinstance(frame, LLMFullResponseStartFrame):
                self._text_parts = []
            elif isinstance(frame, LLMTextFrame):
                text = str(getattr(frame, "text", "") or "")
                if text:
                    self._text_parts.append(text)
            elif isinstance(frame, LLMFullResponseEndFrame):
                text = "".join(self._text_parts).strip()
                if text:
                    log_event(
                        "voice_ai_response",
                        session_id=context.session_id,
                        call_id=context.call_id,
                        transcript=context.latest_transcript,
                        tts_text=text,
                        route=_route_log_payload(context.latest_route),
                        tool_calls=list(context.latest_tool_calls),
                        call_verified=context.call_verified,
                        verified_mobile_last4=context.verified_mobile_last4,
                    )
                self._text_parts = []

            await self.push_frame(frame, direction)

    return StableLlmResponseLogger()
