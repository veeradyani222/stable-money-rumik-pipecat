from __future__ import annotations

import json
import os
from typing import Any

import httpx

from app.core.config import get_settings


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


def _parse_dob_verdict(text: str) -> dict[str, Any] | None:
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
    return {"verdict": verdict, "model_answered": True}


def _dob_verification_model() -> str:
    settings = get_settings()
    return (
        os.getenv("OPENAI_DOB_VERIFICATION_MODEL")
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


async def match_dob_ai(
    caller_utterance: str,
    record_iso_date: str,
    *,
    api_key: str | None = None,
) -> dict[str, Any]:
    utterance = caller_utterance.strip()
    if not utterance:
        return {"verdict": "unclear", "model_answered": False}

    settings = get_settings()
    key = api_key or settings.openai_api_key
    if not key:
        return {"verdict": "unclear", "model_answered": False}

    model = _dob_verification_model()
    body: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": json.dumps(
                    {"caller_utterance": utterance, "record_date_iso": record_iso_date},
                    ensure_ascii=False,
                ),
            }
        ],
        "instructions": "\n".join(
            [
                "You verify whether a banking support caller stated their date of birth matching an internal record.",
                "The record_date_iso is the canonical calendar date on file in YYYY-MM-DD format.",
                "CRITICAL: The caller is based in India. In India the date convention is dd/mm/yyyy; interpret ambiguous numeric dates as day first.",
                "The caller may speak in ANY language, script, or writing system. Handle phonetic Indic-script DOB ASR transcriptions properly.",
                "Example: thirtieth July nineteen ninety three means 1993-07-30. Do not confuse thirtieth with thirty seven.",
                "Accept any natural date expression such as 9 November 1995, 9/11/95, november nine ninety five, or I said 9/11/1995.",
                "Ignore politeness fillers and focus only on the date content.",
                "verdict=match when the caller clearly conveys the same calendar day as record_date_iso.",
                "verdict=no_match when the caller clearly conveys a different calendar day.",
                "verdict=unclear when the utterance has no date content, is gibberish, or the date is too ambiguous to determine.",
                "Do not guess. If you are not confident, return unclear.",
                "Return only the required JSON fields. Do not include explanations or reasoning.",
            ]
        ),
        "max_output_tokens": 256,
        "stream": False,
        "prompt_cache_key": "stable-dob-verification-v2",
        "text": {
            "format": {
                "type": "json_schema",
                "name": "stable_dob_verdict",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "verdict": {"type": "string", "enum": ["match", "no_match", "unclear"]},
                    },
                    "required": ["verdict"],
                },
            }
        },
    }

    json_response = await _post_responses(key, body)
    if not json_response:
        return {"verdict": "unclear", "model_answered": False}
    parsed = _parse_dob_verdict(_extract_json_text(json_response))
    if not parsed:
        return {"verdict": "unclear", "model_answered": False}
    return parsed
