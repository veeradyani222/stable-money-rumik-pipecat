from __future__ import annotations

import re

RUMIK_TONES = ("happy", "excited", "sad", "angry", "neutral", "whisper")
SMALL = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
ORDINALS = {
    1: "first",
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
    9: "ninth",
    10: "tenth",
    11: "eleventh",
    12: "twelfth",
    13: "thirteenth",
    14: "fourteenth",
    15: "fifteenth",
    16: "sixteenth",
    17: "seventeenth",
    18: "eighteenth",
    19: "nineteenth",
    20: "twentieth",
    21: "twenty first",
    22: "twenty second",
    23: "twenty third",
    24: "twenty fourth",
    25: "twenty fifth",
    26: "twenty sixth",
    27: "twenty seventh",
    28: "twenty eighth",
    29: "twenty ninth",
    30: "thirtieth",
    31: "thirty first",
}
COMPATIBLE_EVENTS = {
    "happy": {"laugh", "chuckle"},
    "excited": {"laugh"},
    "sad": {"sigh"},
    "angry": {"sigh"},
    "neutral": set(),
    "whisper": {"chuckle", "sigh"},
}


def _coerce_tone(value: str | None) -> str | None:
    normalized = re.sub(r"[_-]+", " ", (value or "").strip().lower())
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized in RUMIK_TONES:
        return normalized
    for tone in RUMIK_TONES:
        if re.search(rf"\b{tone}\b", normalized):
            return tone
    return None


def _below_hundred(value: int) -> str:
    if value < 20:
        return SMALL[value]
    tens, ones = divmod(value, 10)
    return TENS[tens] if ones == 0 else f"{TENS[tens]} {SMALL[ones]}"


def _below_thousand(value: int) -> str:
    if value < 100:
        return _below_hundred(value)
    hundreds, rest = divmod(value, 100)
    prefix = f"{SMALL[hundreds]} hundred"
    return prefix if rest == 0 else f"{prefix} {_below_hundred(rest)}"


def number_to_indian_words(value: int) -> str:
    if value < 0:
        return ""
    if value < 1000:
        return _below_thousand(value)
    parts: list[str] = []
    for unit_value, unit_name in ((10000000, "crore"), (100000, "lakh"), (1000, "thousand")):
        if value >= unit_value:
            count, value = divmod(value, unit_value)
            parts.append(f"{_below_thousand(count)} {unit_name}")
    if value:
        parts.append(_below_thousand(value))
    return " ".join(parts)


def _year_to_words(value: int) -> str:
    if 1900 <= value <= 1999:
        rest = value - 1900
        return "nineteen hundred" if rest == 0 else f"nineteen {_below_hundred(rest)}"
    if 2000 <= value <= 2009:
        rest = value - 2000
        return "two thousand" if rest == 0 else f"two thousand {_below_hundred(rest)}"
    if 2010 <= value <= 2099:
        return f"twenty {_below_hundred(value - 2000)}"
    return number_to_indian_words(value)


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def _amount_to_words(value: str) -> str:
    digits = _digits_only(value)
    return number_to_indian_words(int(digits)) if digits else value


def _normalize_number_token(token: str) -> str:
    digits = _digits_only(token)
    if not digits:
        return token
    if "," in token or 5 <= len(digits) <= 7:
        return _amount_to_words(token)
    return " ".join(digits)


def _normalize_date(match: re.Match[str]) -> str:
    day = int(match.group(1))
    month = match.group(2)
    year = int(match.group(3))
    return f"{ORDINALS.get(day, _below_hundred(day))} {month} {_year_to_words(year)}"


def _normalize_body(text: str) -> str:
    date_pattern = re.compile(
        r"\b([0-9]{1,2})(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+"
        r"([0-9]{4})\b",
        re.I,
    )
    text = re.sub(
        r"(?:₹\s*([0-9][0-9,]*)|\b(?:rs\.?|inr|rupees?)\s*([0-9][0-9,]*))",
        lambda match: f"rupees {_amount_to_words(match.group(1) or match.group(2) or '')}",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\b([0-9][0-9,]*)\s*(?:rs\.?|inr|rupees?)\b",
        lambda match: f"rupees {_amount_to_words(match.group(1))}",
        text,
        flags=re.I,
    )
    text = date_pattern.sub(_normalize_date, text)
    text = re.sub(
        r"\b([0-9]{1,3})\s+(se|to)\s+([0-9]{1,3})\b",
        lambda match: (
            f"{_below_thousand(int(match.group(1)))} "
            f"{match.group(2).lower()} {_below_thousand(int(match.group(3)))}"
        ),
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\b([0-9]{1,3})\s+(months?|hours?|days?|years?|working hours?)\b",
        lambda match: f"{_below_thousand(int(match.group(1)))} {match.group(2).lower()}",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b[0-9][0-9,]*\b", lambda match: _normalize_number_token(match.group(0)), text)
    text = re.sub(r"[*]+", " ", text)
    text = re.sub(r"[\\/]+", " or ", text)
    text = re.sub(r"[\u2010-\u2015-]+", " ", text)
    text = re.sub(r"[:;]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_rumik_starting_tone(text: str) -> str | None:
    match = re.match(r"^\[([^\]]+)\]\s*", text.strip())
    return _coerce_tone(match.group(1) if match else None)


def normalize_rumik_text(text: str, fallback_tone: str = "neutral") -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    starting_tone = extract_rumik_starting_tone(normalized) or fallback_tone

    def tone_replacer(match: re.Match[str]) -> str:
        tone = _coerce_tone(match.group(1))
        return f"[{starting_tone}]" if match.start() == 0 and tone == starting_tone else ""

    normalized = re.sub(r"\[([^\]]+)\]", tone_replacer, normalized)
    if not re.match(r"^\[(happy|excited|sad|angry|neutral|whisper)\] ", normalized):
        normalized = f"[{starting_tone}] {re.sub(r'^\[[^\]]+\]\s*', '', normalized)}"

    def event_replacer(match: re.Match[str]) -> str:
        event = match.group(1)
        return match.group(0) if event in COMPATIBLE_EVENTS.get(starting_tone, set()) else ""

    normalized = re.sub(r"<([a-z]+)>", event_replacer, normalized)
    match = re.match(r"^(\[(?:happy|excited|sad|angry|neutral|whisper)\] )([\s\S]*)$", normalized)
    if match:
        normalized = f"{match.group(1)}{_normalize_body(match.group(2))}"
    else:
        normalized = _normalize_body(normalized)
    return re.sub(r"\s+", " ", normalized).strip()
