from __future__ import annotations

import os
import re
from datetime import date
from typing import Any

from app.agent.dob_verification_ai import match_dob_ai
from app.agent.mobile_verification_ai import match_mobile_last_four_ai
from app.core.config import get_settings


def digits_only(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _parse_iso(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _extract_numeric_date(text: str) -> date | None:
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text)
    if not match:
        return None
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    if year < 100:
        year += 1900 if year > 30 else 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

NUMBER_WORDS = {
    "one": 1,
    "first": 1,
    "two": 2,
    "second": 2,
    "three": 3,
    "third": 3,
    "four": 4,
    "fourth": 4,
    "five": 5,
    "fifth": 5,
    "six": 6,
    "sixth": 6,
    "seven": 7,
    "seventh": 7,
    "eight": 8,
    "eighth": 8,
    "nine": 9,
    "ninth": 9,
    "ten": 10,
    "tenth": 10,
    "eleven": 11,
    "eleventh": 11,
    "twelve": 12,
    "twelfth": 12,
    "thirteen": 13,
    "thirteenth": 13,
    "fourteen": 14,
    "fourteenth": 14,
    "fifteen": 15,
    "fifteenth": 15,
    "sixteen": 16,
    "sixteenth": 16,
    "seventeen": 17,
    "seventeenth": 17,
    "eighteen": 18,
    "eighteenth": 18,
    "nineteen": 19,
    "nineteenth": 19,
    "twenty": 20,
    "twentieth": 20,
    "thirty": 30,
    "thirtieth": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}


def _word_number(text: str) -> int | None:
    normalized = re.sub(r"[-\s]+", " ", text.lower()).strip()
    if normalized in NUMBER_WORDS:
        return NUMBER_WORDS[normalized]
    parts = normalized.split()
    if len(parts) == 2 and parts[0] in {"twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"}:
        base = NUMBER_WORDS[parts[0]]
        ones = NUMBER_WORDS.get(parts[1])
        if ones and 1 <= ones <= 9:
            return base + ones
    return None


def _year_from_words(text: str) -> int | None:
    normalized = re.sub(r"[-\s]+", " ", text.lower()).strip()
    if normalized.startswith("nineteen "):
        suffix = _word_number(normalized.removeprefix("nineteen "))
        if suffix is not None:
            return 1900 + suffix
    if normalized.startswith("twenty "):
        suffix = _word_number(normalized.removeprefix("twenty "))
        if suffix is not None:
            return 2000 + suffix
    if normalized == "two thousand":
        return 2000
    if normalized.startswith("two thousand "):
        suffix = _word_number(normalized.removeprefix("two thousand "))
        if suffix is not None:
            return 2000 + suffix
    return None


def _extract_spoken_date(text: str) -> date | None:
    lowered = text.lower()
    match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\s+(\d{2,4})\b", lowered)
    if not match:
        match = re.search(r"\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{2,4})\b", lowered)
        if not match:
            return None
        month = MONTHS.get(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
    else:
        day = int(match.group(1))
        month = MONTHS.get(match.group(2))
        year = int(match.group(3))
    if not month:
        return None
    if year < 100:
        year += 1900 if year > 30 else 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _extract_word_date(text: str) -> date | None:
    lowered = re.sub(r"[-,]+", " ", text.lower())
    for month_name in sorted(MONTHS, key=len, reverse=True):
        match = re.search(rf"\b{re.escape(month_name)}\b", lowered)
        if not match:
            continue
        before = lowered[: match.start()].strip()
        after = lowered[match.end() :].strip()
        day_words = " ".join(before.split()[-2:])
        day = _word_number(day_words) or _word_number(" ".join(before.split()[-1:]))
        year = _year_from_words(after)
        if not day or not year:
            continue
        try:
            return date(year, MONTHS[month_name], day)
        except ValueError:
            return None
    return None


def dob_matches(record_iso_date: str, caller_text: Any) -> bool:
    record = _parse_iso(record_iso_date)
    if not record:
        return False
    text = str(caller_text or "")
    parsed = _extract_numeric_date(text) or _extract_spoken_date(text) or _extract_word_date(text)
    return parsed == record


def mobile_last_four_matches(record_last_four: str, caller_text: Any) -> bool:
    return digits_only(caller_text)[-4:] == record_last_four


def _result(ok: bool, summary: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": ok, "summary": summary, "data": data}


def _complete(persona: dict[str, Any]) -> dict[str, Any]:
    return _result(
        True,
        "[neutral] Mobile verification aur date of birth verification complete ho gayi hai.",
        {
            "auth_tier": "Tier B",
            "customer_id": persona["customer_id"],
            "name": persona["name"],
            "verification_step": "complete",
            "verified": True,
            "mobile_step_verified": True,
        },
    )


def _dob_mismatch() -> dict[str, Any]:
    return _result(
        False,
        "[neutral] Date of birth match nahi hua. Kripya date of birth ek baar phir batayein, date, month aur year ke saath.",
        {"auth_tier": "Tier B", "verification_step": "dob_required", "verified": False, "mobile_step_verified": True},
    )


def _dob_unclear() -> dict[str, Any]:
    return _result(
        False,
        "[neutral] Ek baar phir clearly bata dijiye, date, month aur year.",
        {
            "auth_tier": "Tier B",
            "verification_step": "dob_required",
            "verified": False,
            "mobile_step_verified": True,
            "dob_parse_failed": True,
        },
    )


async def verify_read_access(
    persona: dict[str, Any],
    args: dict[str, Any],
    *,
    verified_mobile_last4: str | None = None,
) -> dict[str, Any]:
    gate = digits_only(verified_mobile_last4)[-4:]
    mobile_text = str(args.get("mobile_last_4") or "").strip()
    dob_text = str(args.get("date_of_birth") or "").strip()
    if gate == persona["mobile_last_4"] and dob_text:
        mobile_text = persona["mobile_last_4"]
    if not mobile_text and gate == persona["mobile_last_4"]:
        mobile_text = gate
    if not mobile_text:
        return _result(
            False,
            "[neutral] Account details check karne ke liye mobile number ke last four digits batayein.",
            {"auth_tier": "Tier B", "verification_step": "mobile_last_4_required", "verified": False},
        )

    settings = get_settings()
    ai_enabled = bool(settings.openai_api_key) and os.getenv("STABLE_DISABLE_AI_MOBILE") != "1"
    if ai_enabled:
        ai = await match_mobile_last_four_ai(mobile_text, persona["mobile_last_4"], api_key=settings.openai_api_key)
        mobile_ok = ai.get("verdict") == "match"
        if ai.get("verdict") == "unclear":
            return _result(
                False,
                "[neutral] Samajh nahi aa paya. Kripya last four digits ek baar phir clearly batayein.",
                {"auth_tier": "Tier B", "verification_step": "mobile_last_4_required", "verified": False, "mobile_step_verified": False},
            )
    else:
        mobile_ok = mobile_last_four_matches(persona["mobile_last_4"], mobile_text)
    if not mobile_ok:
        return _result(
            False,
            "[neutral] Mobile last four match nahi hua. Kripya last four digits ek baar phir batayein.",
            {"auth_tier": "Tier B", "verification_step": "mobile_last_4_required", "verified": False, "mobile_step_verified": False},
        )
    if not dob_text:
        return _result(
            True,
            "[neutral] Mobile last four match ho gaya. Apni date of birth batayein.",
            {
                "auth_tier": "Tier B",
                "customer_id": persona["customer_id"],
                "mobile_last_4": persona["mobile_last_4"],
                "verification_step": "dob_required",
                "verified": False,
                "mobile_step_verified": True,
            },
        )
    ai_dob_enabled = bool(settings.openai_api_key) and os.getenv("STABLE_DISABLE_AI_DOB") != "1"
    if ai_dob_enabled:
        ai = await match_dob_ai(dob_text, persona["date_of_birth"], api_key=settings.openai_api_key)
        if ai.get("verdict") == "match":
            return _complete(persona)
        if ai.get("verdict") == "no_match":
            return _dob_mismatch()
        return _dob_unclear()
    if dob_matches(persona["date_of_birth"], dob_text):
        return _complete(persona)
    return _dob_unclear()
