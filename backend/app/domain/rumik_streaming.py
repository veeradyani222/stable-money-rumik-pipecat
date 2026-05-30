from __future__ import annotations

from dataclasses import dataclass

MAX_CHUNK_CHARS = 140


@dataclass
class RumikChunkBuffer:
    pending: str = ""


def create_rumik_chunk_buffer() -> RumikChunkBuffer:
    return RumikChunkBuffer()


def _find_chunk_boundary(text: str) -> int:
    for index, char in enumerate(text):
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if char in ".!?" and (not next_char or next_char.isspace()):
            return index + 1
    if len(text) < MAX_CHUNK_CHARS:
        return -1
    last_space = text.rfind(" ", 0, MAX_CHUNK_CHARS)
    return last_space if last_space > 0 else MAX_CHUNK_CHARS


def push_rumik_text_delta(buffer: RumikChunkBuffer, delta: str) -> list[str]:
    buffer.pending += delta
    chunks: list[str] = []
    while True:
        boundary = _find_chunk_boundary(buffer.pending)
        if boundary < 0:
            break
        chunk = buffer.pending[:boundary].strip()
        buffer.pending = buffer.pending[boundary:].lstrip()
        if chunk:
            chunks.append(chunk)
    return chunks


def flush_rumik_chunk_buffer(buffer: RumikChunkBuffer) -> str:
    chunk = buffer.pending.strip()
    buffer.pending = ""
    return chunk

