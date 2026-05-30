from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pipecat.transports.smallwebrtc.connection import IceServer
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from app.pipecat_pipeline.bot import resolve_call_context, run_bot

router = APIRouter(tags=["pipecat"])


def _ice_server_dicts() -> list[dict[str, Any]]:
    servers: list[dict[str, Any]] = [{"urls": "stun:stun.l.google.com:19302"}]
    turn_host = os.getenv("TURN_HOST")
    if not turn_host:
        return servers

    turn_port = os.getenv("TURN_PORT", "3478")
    username = os.getenv("TURN_USERNAME", "")
    credential = os.getenv("TURN_CREDENTIAL", "")
    turn_servers = [
        {"urls": f"turn:{turn_host}:{turn_port}?transport=tcp", "username": username, "credential": credential},
        {"urls": f"turn:{turn_host}:{turn_port}?transport=udp", "username": username, "credential": credential},
    ]
    return turn_servers + servers


def _ice_servers() -> list[IceServer]:
    return [
        IceServer(
            urls=server["urls"],
            username=server.get("username"),
            credential=server.get("credential"),
        )
        for server in _ice_server_dicts()
    ]


small_webrtc_handler = SmallWebRTCRequestHandler(ice_servers=_ice_servers())


@router.get("/turn-config")
async def turn_config():
    return _ice_server_dicts()


@router.post("/offer")
@router.post("/api/offer")
async def offer(request: SmallWebRTCRequest, background_tasks: BackgroundTasks):
    try:
        small_webrtc_handler.update_ice_servers(_ice_servers())

        async def webrtc_connection_callback(connection):
            context = await resolve_call_context(request.request_data)
            background_tasks.add_task(run_bot, connection, context)

        return await small_webrtc_handler.handle_web_request(
            request=request,
            webrtc_connection_callback=webrtc_connection_callback,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/offer")
@router.patch("/api/offer")
async def ice_candidate(request: SmallWebRTCPatchRequest):
    await small_webrtc_handler.handle_patch_request(request)
    return {"status": "success"}


@router.post("/api/voice/pipecat-session")
async def pipecat_session(body: dict):
    return {
        "ok": True,
        "transport": "smallwebrtc",
        "offer_url": "/api/offer",
        "turn_config_url": "/turn-config",
        "session_id": body.get("session_id"),
        "call_id": body.get("call_id"),
    }


async def close_small_webrtc_handler() -> None:
    await small_webrtc_handler.close()
