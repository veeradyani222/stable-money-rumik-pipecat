from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.domain.policies import STABLE_INTENT_POLICIES, route_for_intent, trace_stable_turn_route

INTENT_IDS = [*STABLE_INTENT_POLICIES, "unknown"]
CLASSIFIER_HISTORY_LIMIT = 4
logger = logging.getLogger(__name__)

INTENT_CLASSIFICATION_GUIDE = {
    "payment.failed": "Payment failed, money debited, FD not booked, amount stuck, refund, or reconciliation.",
    "fd.book.status": "FD booking, booking confirmation, or whether an FD has been created.",
    "fd.withdraw.premature": "Caller wants to break, close, or withdraw an FD before maturity.",
    "kyc.status": "Caller asks about their own KYC status, review, approval, rejection, or next step.",
    "kyc.explainer": "General explanation of what KYC means, not account-specific status.",
    "fd.rates.compare": "Compare FD rates, interest rates, tenure, or issuer options.",
    "maturity.payout.delay": "Matured FD payout delay or maturity amount not received.",
    "app.real.check": "Trust, legitimacy, DICGC, partner bank, or whether Stable Money is real or safe.",
    "ticket.status": "Status of an existing support ticket or complaint ticket.",
    "grievance.escalate": "Complaint, escalation, formal grievance, or unresolved support issue.",
    "support.contact": "Human support contact, support hours, contact page, or grievance contact details.",
    "payment.summary": "General payment history, status, or overview without issue framing.",
    "fd.summary": "Overview of all FDs, FD list, deposit details, or status buckets.",
    "account.overview": "General account status, account snapshot, or verified safe overview.",
    "refund.status": "Refund timing, refund ETA, or refund state.",
    "secure.action.help": "Mobile number change, bank account change, nominee update, or profile modification.",
    "conversation.goodbye": "Caller is ending the conversation, says they are done, or asks to hang up.",
    "unknown": "Unrelated, too unclear, or not enough information to choose a Stable Money support intent.",
}


def _extract_json_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_parsed"), dict):
        return json.dumps(response["output_parsed"])
    if isinstance(response.get("output_text"), str) and response["output_text"].strip():
        return response["output_text"].strip()
    for item in response.get("output") or []:
        if isinstance(item, str) or not isinstance(item, dict):
            continue
        if isinstance(item.get("parsed"), dict):
            return json.dumps(item["parsed"])
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if isinstance(content.get("parsed"), dict):
                return json.dumps(content["parsed"])
            if isinstance(content.get("text"), str) and content["text"].strip():
                return content["text"].strip()
        if isinstance(item.get("text"), str) and item["text"].strip():
            return item["text"].strip()
    return ""


def _parse_intent(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text.strip())
    except (json.JSONDecodeError, AttributeError):
        return None
    intent = parsed.get("intent") if isinstance(parsed, dict) else None
    if intent not in INTENT_IDS:
        return None
    return {"intent": intent, "model_answered": True}


async def _post_responses(api_key: str, body: dict[str, Any]) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
            )
        if response.status_code >= 400:
            return None
        return response.json()
    except Exception:
        return None


async def classify_intent_ai(
    transcript: str,
    history: list[dict[str, str]],
    *,
    api_key: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    key = api_key or settings.openai_api_key
    if not transcript.strip() or not key:
        return {"intent": "unknown", "model_answered": False}

    body: dict[str, Any] = {
        "model": settings.openai_intent_model or settings.openai_agent_model,
        "input": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "transcript": transcript,
                        "recent_history": history[-CLASSIFIER_HISTORY_LIMIT:],
                        "allowed_intents": INTENT_IDS,
                        "intent_classification_guide": INTENT_CLASSIFICATION_GUIDE,
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "instructions": "\n".join(
            [
                "Classify a Stable Money voice-support transcript into exactly one fixed intent.",
                "Use semantic meaning and recent_history context in any language or script, including mixed-language speech.",
                "Preserve the active support intent for follow-ups, corrections, confirmations, and verification answers.",
                "If the latest turn clearly switches topic, classify the new topic.",
                "Return only the required JSON field. Do not include explanations or reasoning.",
            ]
        ),
        "max_output_tokens": 1024,
        "stream": False,
        "prompt_cache_key": "stable-intent-classifier-v2",
        "text": {
            "format": {
                "type": "json_schema",
                "name": "stable_intent_classification",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"intent": {"type": "string", "enum": INTENT_IDS}},
                    "required": ["intent"],
                },
            }
        },
    }
    response = await _post_responses(key, body)
    if not response:
        logger.warning("intent_classifier_no_response")
        return {"intent": "unknown", "model_answered": False}
    classification = _parse_intent(_extract_json_text(response))
    if classification:
        return classification
    incomplete_details = response.get("incomplete_details")
    incomplete_reason = incomplete_details.get("reason") if isinstance(incomplete_details, dict) else None
    logger.warning(
        "intent_classifier_unparseable_response status=%s incomplete_reason=%s response_id=%s",
        response.get("status"),
        incomplete_reason,
        response.get("id"),
    )
    return {"intent": "unknown", "model_answered": False}


async def resolve_stable_turn_route_ai(transcript: str, history: list[dict[str, str]]) -> dict[str, Any]:
    deterministic = trace_stable_turn_route(transcript, history)["route"]
    if deterministic["intent"] != "unknown":
        return deterministic
    classification = await classify_intent_ai(transcript, history)
    return route_for_intent(str(classification.get("intent") or "unknown"))
