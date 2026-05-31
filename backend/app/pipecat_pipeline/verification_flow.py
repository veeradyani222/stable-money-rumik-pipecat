from __future__ import annotations

from typing import Any

VERIFICATION_FLOW_BOUNDARY = ("support", "verify.mobile", "verify.dob", "support")


def create_verification_flow_manager(*, worker: Any, llm: Any, context_aggregator: Any, transport: Any):
    from pipecat_flows import FlowManager

    return FlowManager(
        worker=worker,
        llm=llm,
        context_aggregator=context_aggregator,
        transport=transport,
    )


def verification_flow_nodes() -> dict[str, dict[str, Any]]:
    return {
        "support": {
            "task_messages": [
                {
                    "role": "system",
                    "content": "Route ordinary Stable Money support turns through the existing support router.",
                }
            ],
        },
        "verify.mobile": {
            "task_messages": [
                {
                    "role": "system",
                    "content": "Ask only for the registered mobile number last four digits.",
                }
            ],
        },
        "verify.dob": {
            "task_messages": [
                {
                    "role": "system",
                    "content": "Ask for date of birth, verify it, then resume the pending support route.",
                }
            ],
        },
    }
