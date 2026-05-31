from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

KYC_BADGE_LABELS = {
    "not_started": "KYC - Not started",
    "in_progress": "KYC - In progress",
    "pending_review": "KYC - Pending review",
    "rejected": "KYC - Rejected",
    "approved": "KYC - Approved",
}

PERSONAS: list[dict[str, Any]] = [
    {
        "persona_id": "cust_demo_001",
        "customer_id": "cust_demo_001",
        "name": "Ananya Sharma",
        "mobile_last_4": "3210",
        "date_of_birth": "1991-08-14",
        "kyc_status": "pending_review",
        "kyc_rejection_reason": None,
        "kyc_eta": "usually within 24 working hours",
        "kyc_next_step": "Wait for review completion; no document resubmission needed right now",
        "payments": [
            {
                "payment_reference": "PAY-8831",
                "aliases": ["45791034", "UTR45791034", "pay_45791034"],
                "source_bank": "HDFC",
                "amount": 50000,
                "status": "failed",
                "eta": "FD booking is still in progress; refund usually reflects within 5 working days if booking does not complete",
                "refund_status": "not_initiated",
                "refund_eta": "within 5 working days if booking does not complete",
            }
        ],
        "fixed_deposits": [
            {
                "fd_id": "FD-8110",
                "booking_date": "2026-05-01",
                "bank": "Shriram Finance",
                "amount": 50000,
                "tenure": "12 months",
                "status": "processing",
                "maturity_date": "2027-05-01",
                "expected_confirmation_window": "usually within 24 to 48 working hours",
                "payout_status": None,
                "payout_eta": None,
                "payout_expected_date": None,
                "payout_delay_stage": None,
                "premature_withdrawal_estimate": None,
                "premature_withdrawal_penalty": None,
                "premature_withdrawal_payout_window": None,
            }
        ],
        "open_tickets": [
            {
                "ticket_id": "TKT-10031",
                "issue": "Payment reconciliation follow-up for PAY-8831",
                "priority": "high",
                "status": "open",
                "sla": "within 48 hours",
                "escalation_reason": "User requested follow-up on debited payment",
                "created_at": "2026-05-10T10:30:00+05:30",
            }
        ],
        "secure_links": [],
    },
    {
        "persona_id": "cust_demo_002",
        "customer_id": "cust_demo_002",
        "name": "Rohan Mehta",
        "mobile_last_4": "7741",
        "date_of_birth": "1988-03-22",
        "kyc_status": "rejected",
        "kyc_rejection_reason": "Address proof document was blurry and could not be verified",
        "kyc_eta": None,
        "kyc_next_step": "Resubmit a clear address proof document from the app",
        "payments": [],
        "fixed_deposits": [],
        "open_tickets": [
            {
                "ticket_id": "TKT-10044",
                "issue": "KYC document rejected; customer needs resubmission help",
                "priority": "medium",
                "status": "open",
                "sla": "within 48 hours",
                "escalation_reason": "Customer needs clarity on rejected address proof",
                "created_at": "2026-05-10T12:15:00+05:30",
            }
        ],
        "secure_links": [],
    },
    {
        "persona_id": "cust_demo_003",
        "customer_id": "cust_demo_003",
        "name": "Priya Nair",
        "mobile_last_4": "5598",
        "date_of_birth": "1995-11-09",
        "kyc_status": "approved",
        "kyc_rejection_reason": None,
        "kyc_eta": None,
        "kyc_next_step": None,
        "payments": [
            {
                "payment_reference": "PAY-3345",
                "aliases": ["UTR33450091", "33450091"],
                "source_bank": "HDFC",
                "amount": 75000,
                "status": "settled",
                "eta": None,
                "refund_status": None,
                "refund_eta": None,
            },
        ],
        "fixed_deposits": [
            {
                "fd_id": "FD-3345",
                "booking_date": "2025-05-06",
                "bank": "Mahindra Finance",
                "amount": 75000,
                "tenure": "12 months",
                "status": "matured",
                "maturity_date": "2026-05-06",
                "expected_confirmation_window": None,
                "payout_status": "delayed_follow_up_needed",
                "payout_eta": "usually within 1 to 3 working days",
                "payout_expected_date": "2026-05-09",
                "payout_delay_stage": "T+3 to T+5",
                "premature_withdrawal_estimate": None,
                "premature_withdrawal_penalty": None,
                "premature_withdrawal_payout_window": None,
            },
        ],
        "open_tickets": [
            {
                "ticket_id": "TKT-10052",
                "issue": "Maturity payout delayed beyond expected date for FD-3345",
                "priority": "medium",
                "status": "in_progress",
                "sla": "within 48 hours",
                "escalation_reason": "Maturity payout crossed expected date",
                "created_at": "2026-05-09T15:45:00+05:30",
            }
        ],
        "secure_links": [],
    },
    {
        "persona_id": "cust_demo_004",
        "customer_id": "cust_demo_004",
        "name": "Vikram Patel",
        "mobile_last_4": "2468",
        "date_of_birth": "1990-12-05",
        "kyc_status": "approved",
        "kyc_rejection_reason": None,
        "kyc_eta": None,
        "kyc_next_step": None,
        "payments": [
            {
                "payment_reference": "PAY-4412",
                "aliases": ["UTR44120064", "44120064"],
                "source_bank": "Kotak",
                "amount": 200000,
                "status": "settled",
                "eta": None,
                "refund_status": None,
                "refund_eta": None,
            },
            {
                "payment_reference": "PAY-5148",
                "aliases": ["UTR51482209", "51482209"],
                "source_bank": "HDFC",
                "amount": 60000,
                "status": "settled",
                "eta": None,
                "refund_status": None,
                "refund_eta": None,
            },
        ],
        "fixed_deposits": [
            {
                "fd_id": "FD-4412",
                "booking_date": "2025-01-15",
                "bank": "Shriram Finance",
                "amount": 200000,
                "tenure": "36 months",
                "status": "active",
                "maturity_date": "2028-01-15",
                "expected_confirmation_window": None,
                "payout_status": None,
                "payout_eta": None,
                "payout_expected_date": None,
                "payout_delay_stage": None,
                "premature_withdrawal_estimate": 193000,
                "premature_withdrawal_penalty": 7000,
                "premature_withdrawal_payout_window": "usually within 1 to 3 working days after secure confirmation",
            },
            {
                "fd_id": "FD-5148",
                "booking_date": "2025-12-10",
                "bank": "Mahindra Finance",
                "amount": 60000,
                "tenure": "12 months",
                "status": "active",
                "maturity_date": "2026-12-10",
                "expected_confirmation_window": None,
                "payout_status": None,
                "payout_eta": None,
                "payout_expected_date": None,
                "payout_delay_stage": None,
                "premature_withdrawal_estimate": 58200,
                "premature_withdrawal_penalty": 1800,
                "premature_withdrawal_payout_window": "usually within 1 to 3 working days after secure confirmation",
            },
        ],
        "open_tickets": [],
        "secure_links": [
            {
                "action": "premature_withdrawal",
                "fd_id": "FD-4412",
                "status": "ready_to_send",
                "expires_in": "15 minutes",
            }
        ],
    },
    {
        "persona_id": "cust_demo_005",
        "customer_id": "cust_demo_005",
        "name": "Meera Iyer",
        "mobile_last_4": "8820",
        "date_of_birth": "1986-04-18",
        "kyc_status": "approved",
        "kyc_rejection_reason": None,
        "kyc_eta": None,
        "kyc_next_step": None,
        "payments": [],
        "fixed_deposits": [],
        "open_tickets": [
            {
                "ticket_id": "TKT-10068",
                "issue": "Customer grievance about delayed support response",
                "priority": "high",
                "status": "open",
                "sla": "within 24 hours",
                "escalation_reason": "Existing grievance needs support follow-up",
                "created_at": "2026-05-11T09:20:00+05:30",
            }
        ],
        "secure_links": [],
    },
]


def get_persona_by_id(persona_id: str) -> dict[str, Any] | None:
    for persona in PERSONAS:
        if persona["persona_id"] == persona_id:
            return deepcopy(persona)
    return None


def kyc_badge_label(status: str) -> str:
    return KYC_BADGE_LABELS.get(status, status)


def format_inr(amount: Any) -> str:
    try:
        value = int(amount)
    except (TypeError, ValueError):
        return "-"
    return "₹" + format(value, ",d")


def build_persona_brief(persona: dict[str, Any]) -> dict[str, str]:
    primary_payment = (persona.get("payments") or [None])[0]
    primary_fd = (persona.get("fixed_deposits") or [None])[0]
    ticket = (persona.get("open_tickets") or [None])[0]
    if primary_payment:
        money_line = (
            f"{primary_payment['payment_reference']} from {primary_payment['source_bank']} "
            f"for {format_inr(primary_payment['amount'])} is {primary_payment['status'].replace('_', ' ')}"
        )
    elif primary_fd:
        money_line = (
            f"{primary_fd['fd_id']} with {primary_fd['bank']} for {format_inr(primary_fd['amount'])} "
            f"is {primary_fd['status']}"
        )
    else:
        money_line = "No payment or FD record is attached to this persona"
    return {
        "customerId": persona["customer_id"],
        "name": persona["name"],
        "statusLine": f"{kyc_badge_label(persona['kyc_status'])}"
        + (f" - {persona['kyc_next_step']}" if persona.get("kyc_next_step") else ""),
        "moneyLine": money_line,
        "supportLine": (
            f"{ticket['ticket_id']} is {ticket['status'].replace('_', ' ')} with {ticket['sla']} SLA"
            if ticket
            else "No open support ticket"
        ),
    }


def build_persona_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    persona_id = row.get("persona_id")
    if not persona_id:
        return None
    seed = get_persona_by_id(str(persona_id))
    if not seed:
        return None
    persona = deepcopy(seed)
    for key in (
        "customer_id",
        "name",
        "mobile_last_4",
        "kyc_status",
        "kyc_rejection_reason",
        "kyc_eta",
        "kyc_next_step",
    ):
        if row.get(key) is not None:
            persona[key] = row[key]
    if row.get("date_of_birth") is not None:
        persona["date_of_birth"] = str(row["date_of_birth"])[:10]
    for key in ("payments", "fixed_deposits", "open_tickets", "secure_links"):
        value = row.get(key)
        if isinstance(value, list):
            persona[key] = value
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                persona[key] = parsed
    return persona
