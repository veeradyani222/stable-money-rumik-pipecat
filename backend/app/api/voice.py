from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, Cookie, File, Form, HTTPException, Request, UploadFile

from app.core.config import get_settings
from app.domain.rumik_text import normalize_rumik_text
from app.domain.session_auth import DEMO_SESSION_COOKIE, resolve_demo_session_id

router = APIRouter(prefix="/api/voice", tags=["voice"])

OPENAI_TRANSCRIPT_PROMPT = (
    "Transcribe the complete user utterance from this call audio. Preserve the user language and script as spoken or typed. "
    "Return only transcript text, no markdown, no labels. Do not omit or add words."
)


@router.post("/timing-log")
async def timing_log(body: dict[str, Any]):
    event = body.get("event")
    if not isinstance(event, str) or not event.strip():
        raise HTTPException(status_code=400, detail="Invalid timing event")
    return {"ok": True}


@router.post("/rumik-session")
async def rumik_session(body: dict[str, Any]):
    settings = get_settings()
    if not settings.rumik_api_key:
        raise HTTPException(status_code=500, detail="Missing required environment variable: RUMIK_API_KEY")
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="Missing text")
    rumik_text = normalize_rumik_text(text)[:2000]
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{settings.rumik_base_url}/v1/tts/ws-connect",
            headers={"Authorization": f"Bearer {settings.rumik_api_key}", "Content-Type": "application/json"},
            json={"text": rumik_text, "model": settings.rumik_tts_model},
        )
    try:
        data = response.json()
    except json.JSONDecodeError:
        data = {}
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail={"error": "Could not create Rumik TTS session", "details": data})
    return {**data, "text": rumik_text}


@router.post("/openai-realtime-token")
async def openai_realtime_token(body: dict[str, Any], stable_demo_session: str | None = Cookie(default=None, alias=DEMO_SESSION_COOKIE)):
    session_result = resolve_demo_session_id(body.get("session_id"), stable_demo_session)
    if not session_result["ok"]:
        raise HTTPException(status_code=session_result["status"], detail=session_result["error"])
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="Missing required environment variable: OPENAI_API_KEY")
    request_body = {
        "session": {
            "type": "transcription",
            "audio": {
                "input": {
                    "transcription": {"model": settings.openai_realtime_transcribe_model},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 400,
                        "interrupt_response": False,
                        "create_response": False,
                    },
                }
            },
        }
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/realtime/client_secrets",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
                "OpenAI-Safety-Identifier": f"stable-demo-{session_result['sessionId']}",
            },
            json=request_body,
        )
    data = response.json()
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=data)
    secret = data.get("value") or (data.get("client_secret") or {}).get("value")
    if not secret:
        raise HTTPException(status_code=502, detail="OpenAI Realtime token response was missing a value")
    return {"client_secret": secret, "expires_at": data.get("expires_at") or (data.get("client_secret") or {}).get("expires_at")}


@router.post("/openai-transcribe")
async def openai_transcribe(audio: UploadFile = File(...)):
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="Missing required environment variable: OPENAI_API_KEY")
    data = await audio.read()
    files = {"file": (audio.filename or "utterance.webm", data, audio.content_type or "audio/webm")}
    form = {"model": settings.openai_stt_model, "response_format": "json", "temperature": "0", "prompt": OPENAI_TRANSCRIPT_PROMPT}
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            files=files,
            data=form,
        )
    payload = response.json()
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=payload)
    return {"transcript": str(payload.get("text") or "").strip()}

