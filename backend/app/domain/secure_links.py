from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from app.core.config import get_settings
from app.db.pool import acquire


def _clean(value: Any) -> str:
    return str(value or "").strip().lower()


def _secure_action_url(session_id: str, link: dict[str, Any]) -> str:
    settings = get_settings()
    query = {"session_id": session_id, "action": link.get("action") or ""}
    if link.get("fd_id"):
        query["fd_id"] = link["fd_id"]
    return f"{settings.app_base_url}/secure-action?{urlencode(query)}"


async def send_secure_link_for_session(session_id: str, args: dict[str, Any]) -> dict[str, Any]:
    action = str(args.get("action") or "premature_withdrawal").strip()
    fd_id = args.get("fd_id")
    async with acquire() as connection:
        row = await connection.fetchrow("SELECT email, secure_links FROM demo_users WHERE session_id = $1 LIMIT 1", session_id)
        if not row:
            return {"ok": False, "summary": "Session not found, so I could not send the secure link."}
        raw_links = row.get("secure_links")
        if isinstance(raw_links, str):
            try:
                raw_links = json.loads(raw_links)
            except json.JSONDecodeError:
                raw_links = []
        links = raw_links if isinstance(raw_links, list) else []
        match = next(
            (
                link
                for link in links
                if _clean(link.get("action")) == _clean(action)
                and (not fd_id or link.get("fd_id") == fd_id)
                and link.get("status") == "ready_to_send"
            ),
            None,
        )
        if not match:
            return {
                "ok": False,
                "summary": "[neutral] Is action ke liye ready secure link available nahi hai. Main support ticket create kar sakti hoon.",
                "data": {"state": "not_found"},
            }
        updated = {**match, "status": "sent"}
        updated_links = [updated if item is match else item for item in links]
        await connection.execute(
            "UPDATE demo_users SET secure_links = $2::jsonb WHERE session_id = $1",
            session_id,
            json.dumps(updated_links),
        )
    action_title = action.replace("_", " ")
    return {
        "ok": True,
        "summary": f"[neutral] {action_title} ke liye secure link tayyar hai. Confirmation email thodi der mein aa jayega. Yeh action voice par complete nahi hota.",
        "data": {
            **updated,
            "secure_url": _secure_action_url(session_id, updated),
            "voice_execution_allowed": False,
            "email_pending": True,
            "email_to": row.get("email"),
        },
    }
