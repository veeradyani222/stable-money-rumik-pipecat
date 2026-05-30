from __future__ import annotations

import unittest

from app.pipecat_pipeline.call_context import CallContext
from app.pipecat_pipeline.llm_brain import (
    build_pipecat_tools_schema,
    normalize_tool_args_for_execution,
    register_stable_tool_handlers,
    select_voice_tool_names,
)
from app.domain.policies import route_for_intent


class FakeLlm:
    def __init__(self) -> None:
        self.registered: dict[str | None, object] = {}

    def register_function(self, function_name: str | None, handler: object, **_kwargs: object) -> None:
        self.registered[function_name] = handler


class PipecatLlmBrainTests(unittest.TestCase):
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

    def test_verify_read_access_dob_phase_includes_recent_split_date_parts(self) -> None:
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

        self.assertEqual({"mobile_last_4": "1123", "date_of_birth": "30. July 1993"}, dob_phase)

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

    def test_voice_tool_selection_keeps_account_tool_available_after_verification(self) -> None:
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

        self.assertEqual("route_policy_verify_then_account", scope)
        self.assertEqual(["verify_read_access", "get_payment_reconciliation_status"], tool_names)


class PipecatLlmBrainAsyncTests(unittest.IsolatedAsyncioTestCase):
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
