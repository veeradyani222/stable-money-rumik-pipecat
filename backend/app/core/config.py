from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def load_project_env() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    for env_path in (
        backend_root / ".env.local",
        backend_root / ".env",
    ):
        if env_path.exists():
            load_dotenv(env_path, override=False)


@dataclass(frozen=True)
class Settings:
    database_url: str
    openai_api_key: str
    openai_agent_model: str
    openai_intent_model: str
    openai_stt_model: str
    openai_realtime_transcribe_model: str
    rumik_api_key: str
    rumik_base_url: str
    rumik_tts_model: str
    app_base_url: str
    cors_origin: str


def get_settings() -> Settings:
    load_project_env()
    agent_model = os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini")
    intent_model = os.getenv("OPENAI_INTENT_MODEL") or "gpt-5-mini"
    stt_model = os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")
    return Settings(
        database_url=os.getenv("DATABASE_URL", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_agent_model=agent_model,
        openai_intent_model=intent_model,
        openai_stt_model=stt_model,
        openai_realtime_transcribe_model=os.getenv("OPENAI_REALTIME_TRANSCRIBE_MODEL", stt_model),
        rumik_api_key=os.getenv("RUMIK_API_KEY", ""),
        rumik_base_url=os.getenv("RUMIK_BASE_URL", "https://silk-api.rumik.ai").rstrip("/"),
        rumik_tts_model=os.getenv("RUMIK_TTS_MODEL", "muga"),
        app_base_url=(
            os.getenv("NEXT_PUBLIC_APP_URL")
            or os.getenv("APP_BASE_URL")
            or "http://localhost:3000"
        ).rstrip("/"),
        cors_origin=os.getenv("PYTHON_BACKEND_CORS_ORIGIN", "http://localhost:3000"),
    )


def is_reasoning_model(model: str) -> bool:
    name = model.lower()
    return name.startswith(("gpt-5", "o1", "o3", "o4"))
