from __future__ import annotations

import unittest

from app.domain.policies import route_for_intent
from app.domain.stable_llm_policy import (
    build_stable_agent_instructions,
    select_tool_names_for_request,
    stable_tool_declarations,
)


class StableLlmPolicyTests(unittest.TestCase):
    def test_unverified_tier_b_prompt_exposes_only_verification_tool(self) -> None:
        route = route_for_intent("payment.failed")

        tool_names = select_tool_names_for_request(
            route=route,
            call_verified=False,
            verified_mobile_last4=None,
            transcript="my payment failed and money got debited",
            history=[],
        )
        instructions = build_stable_agent_instructions(
            route=route,
            tool_names=tool_names,
            call_verified=False,
            verified_mobile_last4=None,
        )

        self.assertEqual(["verify_read_access"], tool_names)
        self.assertIn("Never repeat the welcome", instructions)
        self.assertIn("Hard Rumik speech output rule", instructions)
        self.assertIn("Current turn route: payment.failed, Tier B", instructions)
        self.assertIn("Allowed tools: verify_read_access", instructions)
        self.assertIn("Ask only for the registered mobile number last four digits", instructions)
        self.assertNotIn("Allowed tools: verify_read_access, get_payment_reconciliation_status", instructions)

    def test_verified_tier_b_prompt_exposes_account_tool_without_reverification(self) -> None:
        route = route_for_intent("payment.failed")

        tool_names = select_tool_names_for_request(
            route=route,
            call_verified=True,
            verified_mobile_last4="4321",
            transcript="my payment failed",
            history=[],
        )
        instructions = build_stable_agent_instructions(
            route=route,
            tool_names=tool_names,
            call_verified=True,
            verified_mobile_last4="4321",
        )

        self.assertEqual(["get_payment_reconciliation_status"], tool_names)
        self.assertIn("Call verification status: verified", instructions)
        self.assertIn("Do not ask for phone number or date of birth again", instructions)
        self.assertIn("Allowed tools: get_payment_reconciliation_status", instructions)

    def test_tool_declarations_keep_required_arguments(self) -> None:
        declarations = {declaration.name: declaration for declaration in stable_tool_declarations}

        self.assertEqual({}, declarations["verify_read_access"].parameters)
        self.assertIn("issue", declarations["create_support_ticket"].parameters)
        self.assertTrue(declarations["create_support_ticket"].parameters["priority"].optional)
        self.assertEqual("Tier C", declarations["send_secure_link"].auth_tier)


if __name__ == "__main__":
    unittest.main()
