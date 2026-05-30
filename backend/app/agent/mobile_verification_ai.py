from __future__ import annotations

import json
import os
from typing import Any

import httpx

from app.core.config import get_settings, is_reasoning_model


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


def _parse_mobile_verdict(text: str) -> dict[str, Any] | None:
    trimmed = text.strip()
    if not trimmed.startswith("{") or not trimmed.endswith("}"):
        return None
    try:
        parsed = json.loads(trimmed)
    except json.JSONDecodeError:
        return None
    verdict = parsed.get("verdict")
    if verdict not in {"match", "no_match", "unclear"}:
        return None
    raw = "".join(ch for ch in str(parsed.get("extracted_last_four", "")) if ch.isdigit())
    return {
        "verdict": verdict,
        "extracted_last_four": raw if len(raw) == 4 else None,
        "model_answered": True,
    }


def _mobile_verification_model() -> str:
    settings = get_settings()
    return (
        os.getenv("OPENAI_MOBILE_VERIFICATION_MODEL")
        or os.getenv("OPENAI_DOB_VERIFICATION_MODEL")
        or os.getenv("OPENAI_DO_VERIFICATION_MODEL")
        or settings.openai_intent_model
        or settings.openai_agent_model
        or "gpt-5-mini"
    )


async def _post_responses(api_key: str, body: dict[str, Any]) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
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


async def match_mobile_last_four_ai(
    caller_utterance: str,
    record_last_four: str,
    *,
    api_key: str | None = None,
) -> dict[str, Any]:
    utterance = caller_utterance.strip()
    if not utterance or not record_last_four.isdigit() or len(record_last_four) != 4:
        return {"verdict": "unclear", "extracted_last_four": None, "model_answered": False}

    settings = get_settings()
    key = api_key or settings.openai_api_key
    if not key:
        return {"verdict": "unclear", "extracted_last_four": None, "model_answered": False}

    model = _mobile_verification_model()
    body: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": json.dumps(
                    {"caller_utterance": utterance, "record_last_four": record_last_four},
                    ensure_ascii=False,
                ),
            }
        ],
        "instructions": "\n".join(
            [
                "You verify whether a banking support caller stated the last four digits of their registered mobile number.",
                'record_last_four is the canonical four digit string on file; positional order matters, so "1123" is not "2311".',
                "The caller may speak in ANY language, script, or writing system worldwide.",
                "Handle phonetic ASR transcriptions, number words in any language, and creative phrasing like double, triple, or mixed Hinglish.",
                "verdict=match when the caller clearly conveys all four digits in the same order as record_last_four.",
                "verdict=no_match when the caller clearly conveys four digits that differ from record_last_four.",
                "verdict=unclear when the utterance has no digit content, is gibberish, or you cannot confidently determine all four digits.",
                "If you can determine the four digits, return them as a four-digit string in extracted_last_four; otherwise return an empty string.",
                "Do not guess. If you are not confident, return unclear.",
            ]
        ),
        "max_output_tokens": 256,
        "stream": False,
        "prompt_cache_key": "stable-mobile-last4-verification-v1",
        "text": {
            "format": {
                "type": "json_schema",
                "name": "stable_mobile_last_four_verdict",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "verdict": {"type": "string", "enum": ["match", "no_match", "unclear"]},
                        "extracted_last_four": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["verdict", "extracted_last_four", "reason"],
                },
            }
        },
    }
    if is_reasoning_model(model):
        body["reasoning"] = {"effort": "low"}

    json_response = await _post_responses(key, body)
    if not json_response:
        return {"verdict": "unclear", "extracted_last_four": None, "model_answered": False}
    parsed = _parse_mobile_verdict(_extract_json_text(json_response))
    if not parsed:
        return {"verdict": "unclear", "extracted_last_four": None, "model_answered": False}
    return parsed
