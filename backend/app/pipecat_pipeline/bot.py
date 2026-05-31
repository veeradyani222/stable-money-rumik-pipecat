from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.db.pool import acquire
from app.domain.personas import build_persona_from_row
from app.domain.session_auth import (
    get_demo_call_mobile_state_from_store,
    get_demo_call_verified_from_store,
)
from app.pipecat_pipeline.call_context import CallContext
from app.pipecat_pipeline.llm_brain import (
    build_pipecat_tools_schema,
    create_stable_llm_response_logger,
    create_stable_turn_context_processor,
    initial_stable_instructions,
    register_stable_tool_handlers,
)
from app.pipecat_pipeline.rumik_tts import create_pipecat_rumik_tts_service

PERSONA_SELECT_SQL = """
SELECT email, persona_id, customer_id, name, mobile_last_4, date_of_birth::text AS date_of_birth,
       kyc_status, kyc_rejection_reason, kyc_eta, kyc_next_step,
       payments, fixed_deposits, open_tickets, secure_links
FROM demo_users
WHERE session_id = $1
LIMIT 1
"""

STABLE_DEFAULT_OPENING = (
    "[neutral] Namaste, Stable Money support par aapka swagat hai. "
    "Yeh call quality purposes ke liye record ho sakti hai. "
    "Main aapki payment issue, FD status, KYC update, trust check, ya grievance mein help kar sakti hoon."
)
logger = logging.getLogger(__name__)


def _log_voice_event(event: str, **payload: Any) -> None:
    logger.info("%s %s", event, json.dumps({"event": event, **payload}, ensure_ascii=False, default=str))


async def resolve_call_context(request_data: dict[str, Any] | None) -> CallContext:
    payload = request_data or {}
    session_id = str(payload.get("session_id") or payload.get("sessionId") or "")
    call_id = str(payload.get("call_id") or payload.get("callId") or uuid4().hex)
    if len(session_id) < 10:
        raise ValueError("Missing or invalid session_id")

    async with acquire() as connection:
        row = await connection.fetchrow(PERSONA_SELECT_SQL, session_id)
        if not row:
            raise ValueError("Session not found.")
        persona = build_persona_from_row(dict(row))
        if not persona:
            raise ValueError("Persona not selected.")
        verified = await get_demo_call_verified_from_store(connection, session_id, call_id)
        mobile_gate, pending_route = await get_demo_call_mobile_state_from_store(connection, session_id, call_id)

    return CallContext(
        session_id=session_id,
        call_id=call_id,
        persona=persona,
        call_verified=verified,
        verified_mobile_last4=mobile_gate,
        pending_route=pending_route,
    )


async def run_bot(webrtc_connection: Any, context: CallContext) -> None:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required to run the Pipecat voice agent.")

    from pipecat.frames.frames import TTSSpeakFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
    from pipecat.services.openai.responses.llm import OpenAIResponsesLLMService
    from pipecat.services.openai.stt import OpenAIRealtimeSTTService
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
    from pipecat.workers.runner import WorkerRunner

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_out_10ms_chunks=2),
    )
    stt = OpenAIRealtimeSTTService(
        api_key=settings.openai_api_key,
        turn_detection=None,
        settings=OpenAIRealtimeSTTService.Settings(
            model=settings.openai_realtime_transcribe_model,
            language=None,
            prompt="Transcribe the complete user utterance from this Stable Money support call. Return only transcript text.",
            noise_reduction="near_field",
        ),
    )
    llm_context = LLMContext(messages=[], tools=build_pipecat_tools_schema([]))
    context_aggregators = LLMContextAggregatorPair(llm_context, add_tool_change_messages=False)
    user_aggregator = context_aggregators.user()
    assistant_aggregator = context_aggregators.assistant()
    llm = OpenAIResponsesLLMService(
        api_key=settings.openai_api_key,
        settings=OpenAIResponsesLLMService.Settings(
            model=settings.openai_agent_model,
            system_instruction=initial_stable_instructions(context),
            max_completion_tokens=256,
        ),
    )
    register_stable_tool_handlers(llm, context, log_event=_log_voice_event)
    turn_context = create_stable_turn_context_processor(
        context,
        OpenAIResponsesLLMService.Settings,
        log_event=_log_voice_event,
    )
    llm_response_logger = create_stable_llm_response_logger(context, log_event=_log_voice_event)
    tts = create_pipecat_rumik_tts_service()
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            turn_context,
            user_aggregator,
            llm,
            llm_response_logger,
            tts,
            assistant_aggregator,
            transport.output(),
        ]
    )
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
    )

    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(_aggregator, _strategy, message):
        content = str(getattr(message, "content", "") or "").strip()
        if content:
            context.add_user_turn(content)

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(_aggregator, message):
        content = str(getattr(message, "content", "") or "").strip()
        interrupted = bool(getattr(message, "interrupted", False))
        if content and not interrupted:
            context.add_model_turn(content)
        if content:
            _log_voice_event(
                "voice_tts_queued",
                session_id=context.session_id,
                call_id=context.call_id,
                transcript=context.latest_transcript,
                tts_text=content,
                route=context.latest_route,
                tool_calls=list(context.latest_tool_calls),
                interrupted=interrupted,
            )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        _log_voice_event(
            "voice_tts_queued",
            session_id=context.session_id,
            call_id=context.call_id,
            transcript=None,
            tts_text=STABLE_DEFAULT_OPENING,
            route={"intent": "opening"},
            tool_calls=[],
        )
        await worker.queue_frames([TTSSpeakFrame(STABLE_DEFAULT_OPENING, append_to_context=True)])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client):
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()
