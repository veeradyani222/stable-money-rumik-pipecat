from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.db.pool import acquire


def _normalize_issue(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _ticket_id_from_time(now: datetime) -> str:
    return f"TKT-{abs(int(now.timestamp() * 1000)) % 100000:05d}"


def _safe_priority(value: Any) -> str:
    return value if value in {"low", "medium", "high"} else "medium"


def add_or_reuse_support_ticket(existing: list[dict[str, Any]], issue: str, priority: str, now: datetime | None = None) -> dict[str, Any]:
    issue = issue.strip() or "Customer requested support follow-up"
    normalized = _normalize_issue(issue)
    for ticket in existing:
        if ticket.get("status") in {"open", "in_progress"} and _normalize_issue(str(ticket.get("issue") or "")) == normalized:
            return {"created": False, "ticket": ticket, "tickets": existing}
    at = now or datetime.now(timezone.utc)
    ticket = {
        "ticket_id": _ticket_id_from_time(at),
        "issue": issue,
        "priority": _safe_priority(priority),
        "status": "open",
        "sla": "within 48 hours",
        "escalation_reason": "Customer requested support ticket",
        "created_at": at.isoformat(),
    }
    return {"created": True, "ticket": ticket, "tickets": [*existing, ticket]}


async def create_support_ticket_for_session(session_id: str, args: dict[str, Any]) -> dict[str, Any]:
    async with acquire() as connection:
        row = await connection.fetchrow("SELECT email, open_tickets FROM demo_users WHERE session_id = $1 LIMIT 1", session_id)
        if not row:
            return {"ok": False, "summary": "Session not found, so I could not create a support ticket."}
        raw_tickets = row.get("open_tickets")
        if isinstance(raw_tickets, str):
            try:
                raw_tickets = json.loads(raw_tickets)
            except json.JSONDecodeError:
                raw_tickets = []
        existing = raw_tickets if isinstance(raw_tickets, list) else []
        change = add_or_reuse_support_ticket(existing, str(args.get("issue") or ""), _safe_priority(args.get("priority")))
        if change["created"]:
            await connection.execute(
                "UPDATE demo_users SET open_tickets = $2::jsonb WHERE session_id = $1",
                session_id,
                json.dumps(change["tickets"]),
            )
    return {
        "ok": True,
        "summary": "Support ticket create ho gaya hai. Confirmation email thodi der mein aa jayega.",
        "data": {
            **change["ticket"],
            "created": change["created"],
            "email_pending": True,
            "email_to": row.get("email"),
        },
    }
