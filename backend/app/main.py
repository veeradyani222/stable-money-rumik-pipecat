from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import agent, onboarding, pipecat_sessions, voice
from app.core.config import get_settings
from app.core.http_client import close_shared_http_client
from app.core.logging import configure_runtime_logging
from app.db.pool import close_pool


def create_app() -> FastAPI:
    configure_runtime_logging()
    settings = get_settings()
    app = FastAPI(title="Stable Money Rumik Python Backend")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"ok": True, "service": "stable-money-rumik-python"}

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict):
            detail = exc.detail
            content = detail if "error" in detail else {"error": detail.get("detail", "Request failed"), **detail}
        else:
            content = {"error": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

    @app.on_event("shutdown")
    async def shutdown():
        await pipecat_sessions.close_small_webrtc_handler()
        await close_shared_http_client()
        await close_pool()

    app.include_router(onboarding.router)
    app.include_router(agent.router)
    app.include_router(voice.router)
    app.include_router(pipecat_sessions.router)
    return app


app = create_app()
