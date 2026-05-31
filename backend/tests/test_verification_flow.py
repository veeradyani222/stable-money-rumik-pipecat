from __future__ import annotations

import unittest


class VerificationFlowTests(unittest.TestCase):
    def test_verification_flow_declares_verification_only_boundary(self) -> None:
        from app.pipecat_pipeline import verification_flow

        self.assertEqual(
            ("support", "verify.mobile", "verify.dob", "support"),
            verification_flow.VERIFICATION_FLOW_BOUNDARY,
        )

    def test_verification_flow_imports_pipecat_flows_lazily(self) -> None:
        from app.pipecat_pipeline import verification_flow

        self.assertNotIn("pipecat_flows", verification_flow.__dict__)
        self.assertTrue(callable(verification_flow.create_verification_flow_manager))


if __name__ == "__main__":
    unittest.main()
