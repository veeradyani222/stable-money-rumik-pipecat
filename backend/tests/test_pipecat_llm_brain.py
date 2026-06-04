from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.pipecat_pipeline.call_context import CallContext
from app.pipecat_pipeline.llm_brain import (
    ClassifiedTranscriptionFrame,
    build_pipecat_tools_schema,
    create_intent_classifier_processor,
    create_stable_llm_response_logger,
    create_stable_turn_context_processor,
    normalize_tool_args_for_execution,
    preliminary_filler_intent,
    register_stable_tool_handlers,
    resolve_voice_route,
    select_voice_tool_names,
)
from app.domain.policies import route_for_intent


class FakeLlm:
    def __init__(self) -> None:
        self.registered: dict[str | None, object] = {}

    def register_function(self, function_name: str | None, handler: object, **_kwargs: object) -> None:
        self.registered[function_name] = handler


class PipecatLlmBrainTests(unittest.TestCase):
    def test_preliminary_filler_skips_mobile_answer_during_verification(self) -> None:
        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={},
            history=[
                {
                    "role": "model",
                    "text": "Aapki mobile number ke last four digits batayein.",
                },
            ],
            latest_route=route_for_intent("kyc.status"),
            latest_tool_names=["verify_read_access", "get_kyc_status"],
        )

        self.assertIsNone(preliminary_filler_intent(context, "2468"))

    def test_preliminary_filler_skips_dob_answer_during_verification(self) -> None:
        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={},
            verified_mobile_last4="2468",
            pending_route=route_for_intent("kyc.status"),
        )

        self.assertIsNone(preliminary_filler_intent(context, "30th July 1993"))

    def test_pipecat_schema_contains_requested_tools_only(self) -> None:
        schema = build_pipecat_tools_schema(["verify_read_access", "create_support_ticket"])
        tools = {tool.name: tool for tool in schema.standard_tools}

        self.assertEqual(["verify_read_access", "create_support_ticket"], [tool.name for tool in schema.standard_tools])
        self.assertEqual([], tools["verify_read_access"].required)
        self.assertEqual(["issue"], tools["create_support_ticket"].required)
        self.assertIn("priority", tools["create_support_ticket"].properties)

    def test_verify_read_access_args_are_server_gated_by_latest_transcript(self) -> None:
        mobile_phase = normalize_tool_args_for_execution(
            "verify_read_access",
            {"mobile_last_4": "12"},
            latest_transcript="double one two three",
            history=[],
            verified_mobile_last4=None,
        )
        dob_phase = normalize_tool_args_for_execution(
            "verify_read_access",
            {},
            latest_transcript="twentieth August nineteen ninety four",
            history=[],
            verified_mobile_last4="9876",
        )

        self.assertEqual({"mobile_last_4": "double one two three", "date_of_birth": ""}, mobile_phase)
        self.assertEqual(
            {"mobile_last_4": "9876", "date_of_birth": "twentieth August nineteen ninety four"},
            dob_phase,
        )

    def test_verify_read_access_mobile_phase_uses_transcript_over_decoded_digits(self) -> None:
        mobile_phase = normalize_tool_args_for_execution(
            "verify_read_access",
            {"mobile_last_4": "2688"},
            latest_transcript="دو چار چھ آٹھ",
            history=[],
            verified_mobile_last4=None,
        )

        self.assertEqual({"mobile_last_4": "دو چار چھ آٹھ", "date_of_birth": ""}, mobile_phase)

    def test_verify_read_access_dob_phase_uses_transcript_over_decoded_date(self) -> None:
        dob_phase = normalize_tool_args_for_execution(
            "verify_read_access",
            {"mobile_last_4": "2468", "date_of_birth": "1990-12-06"},
            latest_transcript="fifth December nineteen ninety",
            history=[],
            verified_mobile_last4="2468",
        )

        self.assertEqual(
            {"mobile_last_4": "2468", "date_of_birth": "fifth December nineteen ninety"},
            dob_phase,
        )

    def test_verify_read_access_dob_phase_uses_latest_transcript_only(self) -> None:
        dob_phase = normalize_tool_args_for_execution(
            "verify_read_access",
            {},
            latest_transcript="July 1993",
            history=[
                {"role": "model", "text": "Date of birth match nahi hua. Kripya full date, month aur year ke saath batayein."},
                {"role": "user", "text": "30."},
            ],
            verified_mobile_last4="1123",
        )

        self.assertEqual({"mobile_last_4": "1123", "date_of_birth": "July 1993"}, dob_phase)

    def test_verify_read_access_mobile_phase_can_include_recent_split_digit_parts(self) -> None:
        mobile_phase = normalize_tool_args_for_execution(
            "verify_read_access",
            {},
            latest_transcript="do teen",
            history=[
                {"role": "model", "text": "last four digits batayein"},
                {"role": "user", "text": "ek ek"},
            ],
            verified_mobile_last4=None,
        )

        self.assertEqual({"mobile_last_4": "ek ek do teen", "date_of_birth": ""}, mobile_phase)

    def test_registers_handlers_for_declared_stable_tools(self) -> None:
        llm = FakeLlm()
        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={
                "customer_id": "CUST-1",
                "persona_id": "demo",
                "name": "Demo User",
                "mobile_last_4": "9876",
                "date_of_birth": "1994-08-20",
                "kyc_status": "approved",
                "payments": [],
                "fixed_deposits": [],
                "open_tickets": [],
                "secure_links": [],
            },
        )

        register_stable_tool_handlers(llm, context)

        self.assertIn("verify_read_access", llm.registered)
        self.assertIn("get_payment_reconciliation_status", llm.registered)
        self.assertIn("send_secure_link", llm.registered)

    def test_voice_tool_selection_hides_account_tool_until_verification_completes(self) -> None:
        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "9876"},
            call_verified=False,
        )

        tool_names, scope = select_voice_tool_names(
            route=route_for_intent("payment.failed"),
            context=context,
            transcript="my payment failed",
        )

        self.assertEqual("route_policy", scope)
        self.assertEqual(["verify_read_access"], tool_names)

    def test_voice_tool_selection_exposes_account_tool_after_verification_completes(self) -> None:
        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "9876"},
            call_verified=True,
            verified_mobile_last4="9876",
        )

        tool_names, scope = select_voice_tool_names(
            route=route_for_intent("payment.failed"),
            context=context,
            transcript="my payment failed",
        )

        self.assertEqual("route_policy", scope)
        self.assertEqual(["get_payment_reconciliation_status"], tool_names)

    def test_voice_tool_selection_keeps_verification_tool_for_multilingual_last_four_answer(self) -> None:
        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "1123"},
            call_verified=False,
            history=[
                {
                    "role": "model",
                    "text": "Mujhe aapka mobile number verify karne ke liye last four digits chahiye.",
                },
            ],
        )

        tool_names, scope = select_voice_tool_names(
            route={"intent": "unknown", "authTier": "Tier A", "tools": []},
            context=context,
            transcript="\u098f\u0995, \u098f\u0995, \u09a6\u09cb, \u09a4\u09bf\u09a8",
        )

        self.assertEqual("route_policy", scope)
        self.assertEqual(["verify_read_access"], tool_names)

    def test_verified_unknown_route_broad_scope_excludes_reverification_tool(self) -> None:
        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "1123"},
            call_verified=True,
            verified_mobile_last4="1123",
        )

        tool_names, scope = select_voice_tool_names(
            route={"intent": "unknown", "authTier": "Tier A", "tools": []},
            context=context,
            transcript="tell me my kyc",
        )

        self.assertEqual("broad_unknown_llm_scope", scope)
        self.assertNotIn("verify_read_access", tool_names)
        self.assertIn("get_kyc_status", tool_names)


class PipecatLlmBrainAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_intent_classifier_processor_emits_classified_transcription_with_metrics(self) -> None:
        from pipecat.frames.frames import TranscriptionFrame
        from pipecat.processors.frame_processor import FrameDirection

        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "1123"},
        )
        resolved = route_for_intent("fd.summary")
        events: list[tuple[str, dict[str, object]]] = []
        processor = create_intent_classifier_processor(
            context,
            log_event=lambda event, **payload: events.append((event, payload)),
        )
        processor.push_frame = AsyncMock()  # type: ignore[method-assign]
        processor.start_processing_metrics = AsyncMock()  # type: ignore[method-assign]
        processor.stop_processing_metrics = AsyncMock()  # type: ignore[method-assign]

        with patch(
            "app.pipecat_pipeline.llm_brain.resolve_voice_route",
            new=AsyncMock(return_value=(resolved, "classifier")),
        ) as resolve:
            await processor.process_frame(
                TranscriptionFrame("show all my deposits", "user-1", "source-ts", finalized=True),
                FrameDirection.DOWNSTREAM,
            )

        resolve.assert_awaited_once_with(context, "show all my deposits")
        processor.start_processing_metrics.assert_awaited_once()
        processor.stop_processing_metrics.assert_awaited_once()
        classified = processor.push_frame.await_args.args[0]
        self.assertIsInstance(classified, ClassifiedTranscriptionFrame)
        self.assertEqual("show all my deposits", classified.text)
        self.assertEqual("user-1", classified.user_id)
        self.assertEqual("source-ts", classified.timestamp)
        self.assertTrue(classified.finalized)
        self.assertEqual("fd.summary", classified.route["intent"])
        self.assertEqual("classifier", classified.route_source)
        self.assertEqual("voice_intent_classified", events[0][0])

    async def test_turn_context_uses_preclassified_route_without_resolving_again(self) -> None:
        from pipecat.processors.frame_processor import FrameDirection

        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "1123"},
        )

        class Settings:
            def __init__(self, **_kwargs: object) -> None:
                pass

        processor = create_stable_turn_context_processor(
            context,
            Settings,
            log_event=lambda *_args, **_kwargs: None,
        )
        processor.push_frame = AsyncMock()  # type: ignore[method-assign]
        classified = ClassifiedTranscriptionFrame(
            "show all my deposits",
            "user-1",
            "source-ts",
            route=route_for_intent("fd.summary"),
            route_source="classifier",
            finalized=True,
        )

        with patch("app.pipecat_pipeline.llm_brain.resolve_voice_route", new=AsyncMock()) as resolve:
            await processor.process_frame(classified, FrameDirection.DOWNSTREAM)

        resolve.assert_not_awaited()
        self.assertEqual("fd.summary", context.latest_route["intent"])

    async def test_turn_context_starts_neutral_filler_for_verification_answer(self) -> None:
        from pipecat.frames.frames import TranscriptionFrame
        from pipecat.processors.frame_processor import FrameDirection

        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "1123"},
            verified_mobile_last4="1123",
            pending_route=route_for_intent("kyc.status"),
        )
        started_fillers: list[str] = []
        events: list[tuple[str, dict[str, object]]] = []

        class Settings:
            def __init__(self, **_kwargs: object) -> None:
                pass

        processor = create_stable_turn_context_processor(
            context,
            Settings,
            log_event=lambda event, **payload: events.append((event, payload)),
            start_filler_audio=started_fillers.append,
        )
        processor.push_frame = AsyncMock()  # type: ignore[method-assign]

        await processor.process_frame(
            TranscriptionFrame("30th July 1993", "", 0),
            FrameDirection.DOWNSTREAM,
        )

        self.assertEqual(["unknown"], started_fillers)
        self.assertIn(
            (
                "voice_filler_selected",
                {
                    "session_id": "session-1234567890",
                    "call_id": "call-1",
                    "intent": "unknown",
                    "route_source": "verification",
                },
            ),
            events,
        )

    async def test_turn_context_starts_filler_before_waiting_for_route_resolution(self) -> None:
        from pipecat.frames.frames import TranscriptionFrame
        from pipecat.processors.frame_processor import FrameDirection

        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "1123"},
        )
        release_route = asyncio.Event()
        started_fillers: list[str] = []

        async def resolve_after_release(*_args: object, **_kwargs: object) -> tuple[dict[str, object], str]:
            await release_route.wait()
            return route_for_intent("payment.failed"), "router"

        class Settings:
            def __init__(self, **_kwargs: object) -> None:
                pass

        processor = create_stable_turn_context_processor(
            context,
            Settings,
            log_event=lambda *_args, **_kwargs: None,
            start_filler_audio=started_fillers.append,
        )
        processor.push_frame = AsyncMock()  # type: ignore[method-assign]

        with patch("app.pipecat_pipeline.llm_brain.resolve_voice_route", side_effect=resolve_after_release):
            processing = asyncio.create_task(
                processor.process_frame(
                    TranscriptionFrame("my payment failed", "", 0),
                    FrameDirection.DOWNSTREAM,
                )
            )
            await asyncio.sleep(0)

            self.assertEqual(["payment.failed"], started_fillers)
            self.assertFalse(processing.done())

            release_route.set()
            await processing

    async def test_turn_context_waits_for_classifier_before_starting_unknown_filler(self) -> None:
        from pipecat.frames.frames import TranscriptionFrame
        from pipecat.processors.frame_processor import FrameDirection

        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "1123"},
        )
        release_route = asyncio.Event()
        started_fillers: list[str] = []

        async def resolve_after_release(*_args: object, **_kwargs: object) -> tuple[dict[str, object], str]:
            await release_route.wait()
            return route_for_intent("payment.summary"), "router"

        class Settings:
            def __init__(self, **_kwargs: object) -> None:
                pass

        processor = create_stable_turn_context_processor(
            context,
            Settings,
            log_event=lambda *_args, **_kwargs: None,
            start_filler_audio=started_fillers.append,
        )
        processor.push_frame = AsyncMock()  # type: ignore[method-assign]

        with patch("app.pipecat_pipeline.llm_brain.resolve_voice_route", side_effect=resolve_after_release):
            processing = asyncio.create_task(
                processor.process_frame(
                    TranscriptionFrame("\u0928\u0939\u0940\u0902 \u0914\u0930 \u092e\u0947\u0930\u0947 \u092a\u0947\u092e\u0947\u0902\u091f\u094d\u0938 \u0915\u093e \u092c\u0924\u093e\u0913?", "", 0),
                    FrameDirection.DOWNSTREAM,
                )
            )
            await asyncio.sleep(0)

            self.assertEqual([], started_fillers)
            self.assertFalse(processing.done())

            release_route.set()
            await processing

        self.assertEqual(["payment.summary"], started_fillers)

    async def test_turn_context_does_not_start_neutral_filler_when_classifier_stays_unknown(self) -> None:
        from pipecat.frames.frames import TranscriptionFrame
        from pipecat.processors.frame_processor import FrameDirection

        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "1123"},
        )
        started_fillers: list[str] = []
        events: list[tuple[str, dict[str, object]]] = []

        class Settings:
            def __init__(self, **_kwargs: object) -> None:
                pass

        processor = create_stable_turn_context_processor(
            context,
            Settings,
            log_event=lambda event, **payload: events.append((event, payload)),
            start_filler_audio=started_fillers.append,
        )
        processor.push_frame = AsyncMock()  # type: ignore[method-assign]

        with patch(
            "app.pipecat_pipeline.llm_brain.resolve_voice_route",
            new=AsyncMock(return_value=(route_for_intent("unknown"), "classifier")),
        ):
            await processor.process_frame(
                TranscriptionFrame("umm what is this thing", "", 0),
                FrameDirection.DOWNSTREAM,
            )

        self.assertEqual([], started_fillers)
        self.assertIn(
            (
                "voice_filler_skipped",
                {
                    "session_id": "session-1234567890",
                    "call_id": "call-1",
                    "intent": "unknown",
                    "route_source": "classifier",
                    "reason": "unknown_intent",
                },
            ),
            events,
        )

    async def test_voice_route_uses_ai_fallback_resolver(self) -> None:
        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "1123"},
        )
        resolved = route_for_intent("fd.summary")

        with patch(
            "app.pipecat_pipeline.llm_brain.resolve_stable_turn_route_ai",
            new=AsyncMock(return_value=resolved),
        ) as resolve:
            route, source = await resolve_voice_route(context, "show all my deposits")

        self.assertEqual("classifier", source)
        self.assertEqual("fd.summary", route["intent"])
        resolve.assert_awaited_once_with("show all my deposits", [])

    async def test_voice_route_keeps_known_account_route_for_mobile_answer(self) -> None:
        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "2468"},
            latest_route=route_for_intent("kyc.status"),
            latest_tool_names=["verify_read_access", "get_kyc_status"],
            history=[
                {
                    "role": "model",
                    "text": "Pehle aap apne registered mobile number ke last four digits bataiyein.",
                },
            ],
        )

        with patch(
            "app.pipecat_pipeline.llm_brain.resolve_stable_turn_route_ai",
            new=AsyncMock(return_value=route_for_intent("unknown")),
        ) as resolve:
            route, source = await resolve_voice_route(context, "do chaar chhe aath")

        self.assertEqual("verification_route", source)
        self.assertEqual("kyc.status", route["intent"])
        resolve.assert_not_awaited()

    async def test_voice_route_labels_deterministic_keyword_source(self) -> None:
        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "1123"},
        )

        route, source = await resolve_voice_route(context, "refund kab milega")

        self.assertEqual("keyword", source)
        self.assertEqual("refund.status", route["intent"])

    async def test_llm_response_logger_emits_full_ai_text_with_latest_transcript(self) -> None:
        from pipecat.frames.frames import LLMFullResponseEndFrame, LLMFullResponseStartFrame, LLMTextFrame
        from pipecat.processors.frame_processor import FrameDirection

        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={"mobile_last_4": "1123"},
            latest_transcript="payment status batao",
            latest_route=route_for_intent("payment.failed"),
            latest_tool_calls=["get_payment_reconciliation_status"],
        )
        events: list[tuple[str, dict[str, object]]] = []
        processor = create_stable_llm_response_logger(
            context,
            log_event=lambda event, **payload: events.append((event, payload)),
        )
        processor.push_frame = AsyncMock()  # type: ignore[method-assign]

        await processor.process_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
        await processor.process_frame(LLMTextFrame("[neutral] Payment check kar rahi hoon. "), FrameDirection.DOWNSTREAM)
        await processor.process_frame(LLMTextFrame("Aapka paisa safe hai."), FrameDirection.DOWNSTREAM)
        await processor.process_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)

        self.assertEqual(["voice_ai_response"], [event for event, _payload in events])
        payload = events[0][1]
        self.assertEqual("session-1234567890", payload["session_id"])
        self.assertEqual("call-1", payload["call_id"])
        self.assertEqual("payment status batao", payload["transcript"])
        self.assertEqual("[neutral] Payment check kar rahi hoon. Aapka paisa safe hai.", payload["tts_text"])
        self.assertEqual(["get_payment_reconciliation_status"], payload["tool_calls"])

    async def test_verify_success_forces_remaining_original_route_tool(self) -> None:
        llm = FakeLlm()
        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={
                "customer_id": "CUST-1",
                "persona_id": "demo",
                "name": "Demo User",
                "mobile_last_4": "1123",
                "date_of_birth": "1993-07-30",
                "kyc_status": "approved",
                "payments": [],
                "fixed_deposits": [
                    {"fd_id": "FD-1", "bank": "Bank A", "amount": 7000, "status": "booked"},
                    {"fd_id": "FD-2", "bank": "Bank B", "amount": 5000, "status": "booked"},
                ],
                "open_tickets": [],
                "secure_links": [],
            },
            call_verified=False,
            verified_mobile_last4="1123",
            latest_transcript="30th July, 1993",
            latest_route=route_for_intent("fd.summary"),
            latest_tool_names=["verify_read_access"],
        )
        results: list[dict[str, object]] = []
        events: list[tuple[str, dict[str, object]]] = []

        class Params:
            arguments: dict[str, object] = {}

            async def result_callback(self, result: dict[str, object]) -> None:
                results.append(result)

        register_stable_tool_handlers(
            llm,
            context,
            log_event=lambda event, **payload: events.append((event, payload)),
        )

        async def mark_verified(persist_context: CallContext) -> None:
            persist_context.call_verified = True
            persist_context.verified_mobile_last4 = persist_context.persona.get("mobile_last_4")
            persist_context.pending_route = None

        async def match_mobile(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {"verdict": "match", "extracted_last_four": "1123", "model_answered": True}

        async def match_dob(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {"verdict": "match", "model_answered": True}

        with patch("app.pipecat_pipeline.llm_brain._persist_verified_call", new=AsyncMock(side_effect=mark_verified)), patch(
            "app.agent.read_access.match_mobile_last_four_ai",
            side_effect=match_mobile,
        ), patch(
            "app.agent.read_access.match_dob_ai",
            side_effect=match_dob,
        ):
            handler = llm.registered["verify_read_access"]
            await handler(Params())  # type: ignore[operator]

        self.assertEqual(["verify_read_access", "get_fd_summary"], context.latest_tool_calls)
        self.assertEqual(True, results[0]["ok"])
        self.assertIn("FD records available", results[0]["summary"])
        self.assertEqual("get_fd_summary", results[0]["data"]["post_verification_tool"])  # type: ignore[index]
        self.assertEqual(
            ["voice_tool_result", "voice_tool_result"],
            [event for event, _payload in events],
        )
        self.assertEqual("verify_read_access", events[0][1]["tool"])
        self.assertEqual("get_fd_summary", events[1][1]["tool"])

    async def test_send_secure_link_requires_verified_voice_call(self) -> None:
        llm = FakeLlm()
        context = CallContext(
            session_id="session-1234567890",
            call_id="call-1",
            persona={
                "customer_id": "CUST-1",
                "persona_id": "demo",
                "name": "Demo User",
                "mobile_last_4": "9876",
                "date_of_birth": "1994-08-20",
                "kyc_status": "approved",
                "payments": [],
                "fixed_deposits": [],
                "open_tickets": [],
                "secure_links": [],
            },
            call_verified=False,
        )
        results: list[dict[str, object]] = []

        class Params:
            arguments = {"action": "premature_withdrawal"}

            async def result_callback(self, result: dict[str, object]) -> None:
                results.append(result)

        register_stable_tool_handlers(llm, context, log_event=lambda *_args, **_kwargs: None)

        handler = llm.registered["send_secure_link"]
        await handler(Params())  # type: ignore[operator]

        self.assertEqual(False, results[0]["ok"])
        self.assertEqual(True, results[0]["data"]["auth_required"])  # type: ignore[index]
        self.assertEqual("verify_read_access", results[0]["data"]["required_tool"])  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
