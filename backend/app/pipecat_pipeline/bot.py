from __future__ import annotations

import asyncio
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
from app.pipecat_pipeline.filler_audio import create_filler_audio_player
from app.pipecat_pipeline.frame_trace import FrameTraceLogger, create_frame_trace_processor
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


def create_opening_audio_ready_notifier(context: CallContext, *, log_event: Any):
    from pipecat.frames.frames import Frame, OutputTransportMessageUrgentFrame, TTSAudioRawFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class OpeningAudioReadyNotifier(FrameProcessor):
        def __init__(self):
            super().__init__()
            self._notified = False

        async def process_frame(self, frame: Frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if (
                direction == FrameDirection.DOWNSTREAM
                and not self._notified
                and isinstance(frame, TTSAudioRawFrame)
            ):
                self._notified = True
                log_event(
                    "voice_opening_audio_ready",
                    session_id=context.session_id,
                    call_id=context.call_id,
                )
                await self.push_frame(
                    OutputTransportMessageUrgentFrame(
                        {
                            "type": "voice_audio_ready",
                            "phase": "opening",
                            "call_id": context.call_id,
                        }
                    ),
                    direction,
                )
            await self.push_frame(frame, direction)

    return OpeningAudioReadyNotifier()


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
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_out_10ms_chunks=2),
    )
    await run_pipeline(transport, context)


async def bot(runner_args: Any) -> None:
    from pipecat.runner.types import SmallWebRTCRunnerArguments
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

    if not isinstance(runner_args, SmallWebRTCRunnerArguments):
        raise RuntimeError(f"Unsupported Pipecat Cloud runner arguments: {type(runner_args).__name__}")

    context = await resolve_call_context(runner_args.body)
    transport = SmallWebRTCTransport(
        webrtc_connection=runner_args.webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_out_10ms_chunks=2),
    )
    await run_pipeline(transport, context)


async def run_pipeline(transport: Any, context: CallContext) -> None:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required to run the Pipecat voice agent.")

    from pipecat.frames.frames import TTSSpeakFrame
    from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
    from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams
    from pipecat.observers.loggers.metrics_log_observer import MetricsLogObserver
    from pipecat.observers.startup_timing_observer import StartupTimingObserver
    from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
    from pipecat.services.openai.responses.llm import OpenAIResponsesLLMService
    from pipecat.services.openai.stt import OpenAIRealtimeSTTService
    from pipecat.turns.user_mute import FunctionCallUserMuteStrategy, MuteUntilFirstBotCompleteUserMuteStrategy
    from pipecat.turns.user_start import TranscriptionUserTurnStartStrategy, VADUserTurnStartStrategy
    from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
    from pipecat.turns.user_turn_strategies import UserTurnStrategies
    from pipecat.workers.runner import WorkerRunner

    stt = OpenAIRealtimeSTTService(
        api_key=settings.openai_api_key,
        turn_detection=False,
        settings=OpenAIRealtimeSTTService.Settings(
            model=settings.openai_realtime_transcribe_model,
            language=None,
            prompt="Transcribe the complete user utterance from this Stable Money support call. Return only transcript text.",
            noise_reduction="near_field",
        ),
    )
    llm_context = LLMContext(messages=[], tools=build_pipecat_tools_schema([]))
    smart_turn_params = SmartTurnParams(stop_secs=0.8, max_duration_secs=5)
    user_params = LLMUserAggregatorParams(
        vad_analyzer=SileroVADAnalyzer(params=VADParams()),
        user_turn_strategies=UserTurnStrategies(
            start=[VADUserTurnStartStrategy(), TranscriptionUserTurnStartStrategy()],
            stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3(params=smart_turn_params))],
        ),
        user_mute_strategies=[
            MuteUntilFirstBotCompleteUserMuteStrategy(),
            FunctionCallUserMuteStrategy(),
        ],
    )
    context_aggregators = LLMContextAggregatorPair(
        llm_context,
        user_params=user_params,
        add_tool_change_messages=False,
    )
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
    output_transport = transport.output()
    start_filler_audio = None
    _log_voice_event(
        "voice_pipeline_configured",
        session_id=context.session_id,
        call_id=context.call_id,
        enable_filler_audio=settings.enable_filler_audio,
    )
    if settings.enable_filler_audio:
        filler_audio_player = create_filler_audio_player(
            output=output_transport,
            context=context,
            log_event=_log_voice_event,
        )
        start_filler_audio = filler_audio_player.start
    turn_context = create_stable_turn_context_processor(
        context,
        OpenAIResponsesLLMService.Settings,
        log_event=_log_voice_event,
        start_filler_audio=start_filler_audio,
    )
    llm_response_logger = create_stable_llm_response_logger(context, log_event=_log_voice_event)
    tts = create_pipecat_rumik_tts_service()
    opening_audio_ready_notifier = create_opening_audio_ready_notifier(context, log_event=_log_voice_event)
    frame_trace_logger = FrameTraceLogger(context)
    frame_trace_processor = create_frame_trace_processor(context, trace=frame_trace_logger)
    rumik_preconnect_task = asyncio.create_task(tts.preconnect())

    def _log_rumik_preconnect_result(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        if exc := task.exception():
            _log_voice_event(
                "voice_rumik_preconnect_failed",
                session_id=context.session_id,
                call_id=context.call_id,
                error=str(exc),
            )

    rumik_preconnect_task.add_done_callback(_log_rumik_preconnect_result)
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
            opening_audio_ready_notifier,
            frame_trace_processor,
            output_transport,
        ]
    )
    metrics_observer = MetricsLogObserver()
    latency_observer = UserBotLatencyObserver()
    startup_observer = StartupTimingObserver()
    worker = PipelineWorker(
        pipeline,
        observers=[metrics_observer, latency_observer, startup_observer],
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
    )

    @latency_observer.event_handler("on_latency_measured")
    async def on_latency_measured(_observer, latency_seconds):
        _log_voice_event(
            "voice_latency_measured",
            session_id=context.session_id,
            call_id=context.call_id,
            latency_seconds=latency_seconds,
        )

    @latency_observer.event_handler("on_latency_breakdown")
    async def on_latency_breakdown(_observer, breakdown):
        _log_voice_event(
            "voice_latency_breakdown",
            session_id=context.session_id,
            call_id=context.call_id,
            breakdown=breakdown,
        )

    @latency_observer.event_handler("on_first_bot_speech_latency")
    async def on_first_bot_speech_latency(_observer, latency_seconds):
        _log_voice_event(
            "voice_first_bot_speech_latency",
            session_id=context.session_id,
            call_id=context.call_id,
            latency_seconds=latency_seconds,
        )

    @startup_observer.event_handler("on_startup_timing_report")
    async def on_startup_timing_report(_observer, report):
        _log_voice_event(
            "voice_startup_timing_report",
            session_id=context.session_id,
            call_id=context.call_id,
            report=report,
        )

    @startup_observer.event_handler("on_transport_timing_report")
    async def on_transport_timing_report(_observer, report):
        _log_voice_event(
            "voice_transport_timing_report",
            session_id=context.session_id,
            call_id=context.call_id,
            report=report,
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
        frame_trace_logger.log("end_of_call", reason="client_disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()
