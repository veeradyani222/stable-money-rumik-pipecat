from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import quote

import httpx
from websockets.asyncio.client import connect as websockets_connect

from app.core.config import get_settings
from app.domain.rumik_text import normalize_rumik_text

RUMIK_SAMPLE_RATE = 24000


class RumikTTSService:
    """Small adapter used by the Pipecat bot.

    The class avoids importing Pipecat at module import time. `as_pipecat_service`
    returns a real Pipecat TTSService only when the media pipeline starts.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def create_session(self, text: str) -> dict[str, Any]:
        if not self.settings.rumik_api_key:
            raise RuntimeError("RUMIK_API_KEY is required for Rumik TTS")
        rumik_text = normalize_rumik_text(text)[:2000]
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.settings.rumik_base_url}/v1/tts/ws-connect",
                headers={"Authorization": f"Bearer {self.settings.rumik_api_key}", "Content-Type": "application/json"},
                json={"text": rumik_text, "model": self.settings.rumik_tts_model},
            )
        data = response.json()
        if response.status_code >= 400:
            raise RuntimeError(f"Rumik session failed: {data}")
        return {**data, "text": rumik_text}

    async def pcm_chunks(self, text: str) -> AsyncGenerator[bytes, None]:
        session = await self.create_session(text)
        ws_url = session.get("ws_url")
        token = session.get("token")
        if not ws_url or not token:
            raise RuntimeError(f"Rumik session response missing ws_url/token: {session}")
        async with websockets_connect(f"{ws_url}?token={quote(str(token))}") as socket:
            await socket.send(json.dumps({"text": session["text"], "speaker_id": 0}))
            while True:
                message = await socket.recv()
                if isinstance(message, str):
                    try:
                        if json.loads(message).get("type") == "done":
                            break
                    except json.JSONDecodeError:
                        continue
                elif message:
                    yield bytes(message)


def create_pipecat_rumik_tts_service():
    from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
    from pipecat.services.settings import TTSSettings
    from pipecat.services.tts_service import TTSService

    adapter = RumikTTSService()

    class PipecatRumikTTSService(TTSService):
        def __init__(self):
            super().__init__(
                sample_rate=RUMIK_SAMPLE_RATE,
                push_start_frame=True,
                push_stop_frames=True,
                settings=TTSSettings(model=adapter.settings.rumik_tts_model, voice=None, language=None),
            )

        def can_generate_metrics(self) -> bool:
            return True

        async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
            try:
                await self.start_tts_usage_metrics(text)
                async for audio in adapter.pcm_chunks(text):
                    await self.stop_ttfb_metrics()
                    yield TTSAudioRawFrame(audio, RUMIK_SAMPLE_RATE, 1, context_id=context_id)
            except Exception as exc:
                yield ErrorFrame(error=f"Rumik TTS failed: {exc}")

    return PipecatRumikTTSService()

