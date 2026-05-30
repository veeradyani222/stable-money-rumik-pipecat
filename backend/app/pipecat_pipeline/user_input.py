from __future__ import annotations


def normalize_transcript(text: str) -> str:
    return " ".join(text.strip().split())


def is_useful_transcript(text: str) -> bool:
    return len(normalize_transcript(text)) >= 2

