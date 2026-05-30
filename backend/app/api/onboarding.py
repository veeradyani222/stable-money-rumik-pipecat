from __future__ import annotations

import json
import re
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response

from app.db.pool import acquire
from app.domain.personas import get_persona_by_id
from app.domain.session_auth import DEMO_SESSION_COOKIE

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def _clear_call_verification(connection, session_id: str) -> None:
    try:
        await connection.execute("DELETE FROM demo_call_verifications WHERE session_id = $1", session_id)
        await connection.execute("DELETE FROM demo_call_mobile_verifications WHERE session_id = $1", session_id)
    except Exception:
        pass


def _date_or_none(value):
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return None


@router.post("/init")
async def init_onboarding(body: dict, response: Response):
    email_raw = body.get("email")
    if not isinstance(email_raw, str) or not EMAIL_RE.match(email_raw.strip()):
        raise HTTPException(status_code=400, detail="Please enter a valid email address")
    email = email_raw.strip().lower()
    session_id = str(uuid4())
    async with acquire() as connection:
        async with connection.transaction():
            existing = await connection.fetchrow(
                """
                SELECT session_id, persona_id
                FROM demo_users
                WHERE email = $1
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                FOR UPDATE
                """,
                email,
            )
            persona_id = None
            if existing:
                await _clear_call_verification(connection, existing["session_id"])
                row = await connection.fetchrow(
                    """
                    UPDATE demo_users
                    SET session_id = $1
                    WHERE session_id = $2
                    RETURNING persona_id
                    """,
                    session_id,
                    existing["session_id"],
                )
                persona_id = row.get("persona_id") if row else existing.get("persona_id")
            else:
                row = await connection.fetchrow(
                    "INSERT INTO demo_users (session_id, email) VALUES ($1, $2) RETURNING persona_id",
                    session_id,
                    email,
                )
                persona_id = row.get("persona_id") if row else None
    response.set_cookie(DEMO_SESSION_COOKIE, session_id, httponly=True, samesite="lax", path="/", max_age=60 * 60 * 24)
    return {"session_id": session_id, "persona_id": persona_id}


@router.post("/select-persona")
async def select_persona(body: dict, response: Response):
    session_id = body.get("session_id")
    persona_id = body.get("persona_id")
    if not isinstance(session_id, str) or len(session_id) < 10:
        raise HTTPException(status_code=400, detail="Missing or invalid session_id")
    if not isinstance(persona_id, str) or not persona_id.strip():
        raise HTTPException(status_code=400, detail="Missing persona_id")
    persona = get_persona_by_id(persona_id.strip())
    if not persona:
        raise HTTPException(status_code=400, detail="Unknown persona")

    primary_payment = (persona["payments"] or [None])[0]
    primary_fd = (persona["fixed_deposits"] or [None])[0]
    payment_references = [primary_payment["payment_reference"], *primary_payment["aliases"]] if primary_payment else None
    async with acquire() as connection:
        async with connection.transaction():
            result = await connection.execute(
                """
                UPDATE demo_users SET
                  persona_id = $2,
                  intent_id = NULL,
                  customer_id = $3,
                  name = $4,
                  mobile_last_4 = $5,
                  date_of_birth = $6::date,
                  kyc_status = $7,
                  kyc_rejection_reason = $8,
                  kyc_eta = $9,
                  kyc_next_step = $10,
                  payments = $11::jsonb,
                  payment_references = $12::jsonb,
                  source_bank = $13,
                  payment_amount = $14,
                  payment_status = $15,
                  payment_eta = $16,
                  refund_status = $17,
                  refund_eta = $18,
                  fixed_deposits = $19::jsonb,
                  fd_id = $20,
                  fd_booking_date = $21::date,
                  fd_bank = $22,
                  fd_amount = $23,
                  fd_tenure = $24,
                  fd_status = $25,
                  fd_maturity_date = $26::date,
                  fd_expected_confirmation_window = $27,
                  payout_status = $28,
                  payout_eta = $29,
                  payout_expected_date = $30::date,
                  payout_delay_stage = $31,
                  premature_withdrawal_estimate = $32,
                  premature_withdrawal_penalty = $33,
                  premature_withdrawal_payout_window = $34,
                  open_tickets = CASE
                    WHEN persona_id = $2 AND open_tickets IS NOT NULL THEN open_tickets
                    ELSE $35::jsonb
                  END,
                  secure_links = $36::jsonb
                WHERE session_id = $1
                """,
                session_id,
                persona["persona_id"],
                persona["customer_id"],
                persona["name"],
                persona["mobile_last_4"],
                _date_or_none(persona["date_of_birth"]),
                persona["kyc_status"],
                persona["kyc_rejection_reason"],
                persona["kyc_eta"],
                persona["kyc_next_step"],
                json.dumps(persona["payments"]),
                json.dumps(payment_references) if payment_references else None,
                primary_payment.get("source_bank") if primary_payment else None,
                primary_payment.get("amount") if primary_payment else None,
                primary_payment.get("status") if primary_payment else None,
                primary_payment.get("eta") if primary_payment else None,
                primary_payment.get("refund_status") if primary_payment else None,
                primary_payment.get("refund_eta") if primary_payment else None,
                json.dumps(persona["fixed_deposits"]),
                primary_fd.get("fd_id") if primary_fd else None,
                _date_or_none(primary_fd.get("booking_date")) if primary_fd else None,
                primary_fd.get("bank") if primary_fd else None,
                primary_fd.get("amount") if primary_fd else None,
                primary_fd.get("tenure") if primary_fd else None,
                primary_fd.get("status") if primary_fd else None,
                _date_or_none(primary_fd.get("maturity_date")) if primary_fd else None,
                primary_fd.get("expected_confirmation_window") if primary_fd else None,
                primary_fd.get("payout_status") if primary_fd else None,
                primary_fd.get("payout_eta") if primary_fd else None,
                _date_or_none(primary_fd.get("payout_expected_date")) if primary_fd else None,
                primary_fd.get("payout_delay_stage") if primary_fd else None,
                primary_fd.get("premature_withdrawal_estimate") if primary_fd else None,
                primary_fd.get("premature_withdrawal_penalty") if primary_fd else None,
                primary_fd.get("premature_withdrawal_payout_window") if primary_fd else None,
                json.dumps(persona["open_tickets"]),
                json.dumps(persona["secure_links"]),
            )
            if result.endswith("0"):
                raise HTTPException(status_code=404, detail="Session not found")
            await _clear_call_verification(connection, session_id)
    response.set_cookie(DEMO_SESSION_COOKIE, session_id, httponly=True, samesite="lax", path="/", max_age=60 * 60 * 24)
    return {"ok": True}
