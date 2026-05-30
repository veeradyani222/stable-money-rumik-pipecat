from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.agent.read_access import verify_read_access
from app.domain.policies import CANONICAL_SLAS, DEMO_FD_RATES, DISCLOSURE_COPY, SUPPORT_CONTACT, TRUST_FACTS

ToolCallback = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

TOOL_AUTH_TIERS = {
    "verify_read_access": "Tier B",
    "lookup_customer_profile": "Tier B",
    "get_trust_facts": "Tier A",
    "get_canonical_slas": "Tier A",
    "get_disclosure_copy": "Tier A",
    "get_fd_booking_status": "Tier B",
    "get_payment_reconciliation_status": "Tier B",
    "get_kyc_status": "Tier B",
    "get_premature_withdrawal_quote": "Tier B",
    "get_support_ticket_status": "Tier B",
    "get_payment_summary": "Tier B",
    "get_fd_summary": "Tier B",
    "get_refund_status": "Tier B",
    "get_fd_rates": "Tier A",
    "get_account_overview": "Tier A",
    "create_support_ticket": "Tier A/B",
    "send_secure_link": "Tier C",
    "get_support_contact": "Tier A",
}

ALIASES = {
    "check_payment_status": "get_payment_reconciliation_status",
    "check_fd_status": "get_fd_booking_status",
    "check_kyc_status": "get_kyc_status",
    "check_ticket_status": "get_support_ticket_status",
    "get_ticket_status": "get_support_ticket_status",
    "prepare_secure_link": "send_secure_link",
    "create_grievance_ticket": "create_support_ticket",
}


def canonical_tool_name(tool_name: str) -> str:
    return ALIASES.get(tool_name, tool_name)


def tool_result(ok: bool, summary: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": ok, "summary": summary}
    if data is not None:
        result["data"] = data
    return result


def _requires_verified_read(tool_name: str) -> bool:
    return TOOL_AUTH_TIERS.get(canonical_tool_name(tool_name)) in {"Tier B", "Tier C"} and canonical_tool_name(tool_name) not in {
        "verify_read_access",
        "send_secure_link",
    }


def _spoken_status(value: Any) -> str:
    return str(value or "").replace("_", " ")


def _format_rumik_inr(value: Any) -> str:
    try:
        return "rupees " + format(int(value), ",d")
    except (TypeError, ValueError):
        return "rupees zero"


def _clean(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _payment_matches(payment: dict[str, Any], reference: Any) -> bool:
    needle = _clean(reference)
    amount = _digits(reference)
    return (
        not needle
        or _clean(payment.get("payment_reference")) == needle
        or any(_clean(alias) == needle for alias in payment.get("aliases") or [])
        or _clean(payment.get("source_bank")) == needle
        or (amount and _digits(payment.get("amount")) == amount)
    )


def _fd_matches(fd: dict[str, Any], reference: Any) -> bool:
    needle = _clean(reference)
    amount = _digits(reference)
    return (
        not needle
        or _clean(fd.get("fd_id")) == needle
        or _clean(fd.get("bank")) == needle
        or (amount and _digits(fd.get("amount")) == amount)
    )


def _payment_lookup(persona: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    payments = persona.get("payments") or []
    reference = args.get("reference")
    payment = next((item for item in payments if _payment_matches(item, reference)), None)
    if not payment and len(payments) == 1:
        payment = payments[0]
    if not payment:
        return tool_result(False, "[neutral] Is customer ke liye matching payment record nahi mila.", {"intent_id": "payment.failed", "match_count": 0})
    eta = payment.get("eta") or ""
    return tool_result(
        True,
        f"[neutral] {payment['payment_reference']} {payment['source_bank']} se {_format_rumik_inr(payment['amount'])} ka payment {_spoken_status(payment['status'])} hai. {eta}".strip(),
        {"intent_id": "payment.failed", **payment},
    )


def _refund_lookup(persona: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    payments = persona.get("payments") or []
    payment = next((item for item in payments if _payment_matches(item, args.get("reference"))), None)
    if not payment and len(payments) == 1:
        payment = payments[0]
    if not payment or not payment.get("refund_status"):
        return tool_result(False, "[neutral] Refund record abhi available nahi hai.", {"intent_id": "refund.status", "match_count": 0})
    return tool_result(
        True,
        f"[neutral] Refund status {_spoken_status(payment['refund_status'])} hai. {payment.get('refund_eta') or ''}".strip(),
        {"intent_id": "refund.status", **payment},
    )


def _fd_lookup(persona: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    fds = persona.get("fixed_deposits") or []
    fd = next((item for item in fds if _fd_matches(item, args.get("fd_id"))), None)
    if not fd and len(fds) == 1:
        fd = fds[0]
    if not fd:
        return tool_result(False, "[neutral] Is customer ke liye matching FD record nahi mila.", {"intent_id": "fd.book.status", "match_count": 0})
    timeline = fd.get("expected_confirmation_window") or fd.get("payout_eta") or ""
    return tool_result(
        True,
        f"[neutral] {fd['fd_id']} {fd['bank']} mein {_format_rumik_inr(fd['amount'])} ki FD {_spoken_status(fd['status'])} hai. {timeline}".strip(),
        {"intent_id": "fd.book.status", **fd},
    )


def _withdrawal_quote(persona: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    candidates = [fd for fd in persona.get("fixed_deposits") or [] if fd.get("premature_withdrawal_estimate") is not None]
    matches = [fd for fd in candidates if _fd_matches(fd, args.get("fd_id"))]
    if not matches and len(candidates) > 1 and not args.get("fd_id"):
        return tool_result(False, "[neutral] Premature withdrawal quote ke liye kaunsi FD check karni hai? FD code, bank, ya amount bata dijiye.", {"state": "clarification_required", "match_count": len(candidates)})
    fd = (matches or candidates or [None])[0]
    if not fd:
        return tool_result(False, "[neutral] Is FD ke liye premature withdrawal quote available nahi hai.", {"state": "not_found"})
    return tool_result(
        True,
        f"[neutral] {fd['fd_id']} ka premature withdrawal estimate {_format_rumik_inr(fd['premature_withdrawal_estimate'])} hai. Estimated penalty {_format_rumik_inr(fd['premature_withdrawal_penalty'])} hai. Yeh sirf quote hai, withdrawal voice par execute nahi hoga.",
        {
            "intent_id": "fd.withdraw.premature",
            "fd_id": fd["fd_id"],
            "bank": fd["bank"],
            "estimated_value": fd["premature_withdrawal_estimate"],
            "penalty": fd["premature_withdrawal_penalty"],
            "payout_window": fd.get("premature_withdrawal_payout_window"),
            "voice_execution_allowed": False,
        },
    )


def _ticket_status(persona: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    tickets = persona.get("open_tickets") or []
    ticket_id = _clean(args.get("ticket_id"))
    ticket = next((item for item in tickets if not ticket_id or _clean(item.get("ticket_id")) == ticket_id), None)
    if not ticket and len(tickets) == 1:
        ticket = tickets[0]
    if not ticket:
        return tool_result(False, "[neutral] Aap ke liye koi open support ticket nahi mila.", {"intent_id": "ticket.status", "match_count": 0})
    return tool_result(
        True,
        f"[neutral] {ticket['ticket_id']} {_spoken_status(ticket['status'])} hai, issue {ticket['issue']} ke liye. SLA {ticket['sla']} hai.",
        {"intent_id": "ticket.status", **ticket},
    )


async def execute_tool_with_context(
    persona: dict[str, Any],
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    call_verified: bool = False,
    verified_mobile_last4: str | None = None,
    create_support_ticket: ToolCallback | None = None,
    send_secure_link: ToolCallback | None = None,
) -> dict[str, Any]:
    canonical = canonical_tool_name(tool_name)
    args = args or {}
    if _requires_verified_read(canonical) and not call_verified:
        return tool_result(
            False,
            "[neutral] Is account specific tool ke liye pehle read access verification zaroori hai.",
            {"auth_required": True, "required_tool": "verify_read_access", "auth_tier": TOOL_AUTH_TIERS.get(canonical)},
        )
    if canonical == "create_support_ticket" and create_support_ticket:
        return await create_support_ticket(args)
    if canonical == "send_secure_link" and send_secure_link:
        return await send_secure_link(args)
    if canonical == "verify_read_access":
        return await verify_read_access(persona, args, verified_mobile_last4=verified_mobile_last4)
    return execute_tool(persona, canonical, args, call_verified=call_verified)


def execute_tool(
    persona: dict[str, Any],
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    call_verified: bool = False,
) -> dict[str, Any]:
    canonical = canonical_tool_name(tool_name)
    args = args or {}
    if _requires_verified_read(canonical) and not call_verified:
        return tool_result(False, "[neutral] Is account specific tool ke liye pehle read access verification zaroori hai.", {"auth_required": True})
    if canonical == "lookup_customer_profile":
        return tool_result(
            True,
            f"[neutral] {persona['name']} ka profile mil gaya. Sirf masked ya last four identifiers hi read back karne hain.",
            {
                "customer_id": persona["customer_id"],
                "name": persona["name"],
                "mobile_last_4": persona["mobile_last_4"],
                "masked_mobile": f"******{persona['mobile_last_4']}",
                "kyc_status": persona["kyc_status"],
                "open_ticket_count": len(persona.get("open_tickets") or []),
            },
        )
    if canonical == "get_trust_facts":
        return tool_result(True, "[neutral] Stable Money Stable Alpha Technologies Private Limited operate karti hai. FDs RBI regulated partner bank ke saath directly held hain.", {**TRUST_FACTS, "intent_id": "app.real.check"})
    if canonical == "get_canonical_slas":
        return tool_result(True, "[neutral] Approved service timelines load ho gayi hain.", dict(CANONICAL_SLAS))
    if canonical == "get_disclosure_copy":
        topic = str(args.get("topic") or "fd").replace("-", "_")
        copy = DISCLOSURE_COPY.get(topic) or DISCLOSURE_COPY["fd"]
        return tool_result(True, f"[neutral] {copy}", {"topic": topic, "copy": copy})
    if canonical == "get_payment_reconciliation_status":
        return _payment_lookup(persona, args)
    if canonical == "get_refund_status":
        return _refund_lookup(persona, args)
    if canonical == "get_fd_booking_status":
        return _fd_lookup(persona, args)
    if canonical == "get_kyc_status":
        detail = persona.get("kyc_next_step") or persona.get("kyc_rejection_reason") or persona.get("kyc_eta") or "Abhi koi action needed nahi hai."
        return tool_result(
            True,
            f"[neutral] Aapka KYC {_spoken_status(persona['kyc_status'])} hai. {detail}",
            {
                "intent_id": "kyc.status",
                "kyc_status": persona["kyc_status"],
                "kyc_next_step": persona.get("kyc_next_step"),
                "kyc_eta": persona.get("kyc_eta"),
                "kyc_rejection_reason": persona.get("kyc_rejection_reason"),
            },
        )
    if canonical == "get_premature_withdrawal_quote":
        return _withdrawal_quote(persona, args)
    if canonical == "get_support_ticket_status":
        return _ticket_status(persona, args)
    if canonical == "get_payment_summary":
        return tool_result(True, "[neutral] Payment records available hain.", {"intent_id": "payment.summary", "payments": persona.get("payments") or []})
    if canonical == "get_fd_summary":
        return tool_result(True, "[neutral] FD records available hain.", {"intent_id": "fd.summary", "fixed_deposits": persona.get("fixed_deposits") or []})
    if canonical == "get_account_overview":
        return tool_result(
            True,
            f"[neutral] Aapka account overview yeh hai. KYC {_spoken_status(persona['kyc_status'])} hai. Fixed deposits {len(persona.get('fixed_deposits') or [])} hain, payments {len(persona.get('payments') or [])} hain, aur open tickets {len(persona.get('open_tickets') or [])} hain.",
            {
                "intent_id": "account.overview",
                "kyc_status": persona["kyc_status"],
                "fixed_deposit_count": len(persona.get("fixed_deposits") or []),
                "payment_count": len(persona.get("payments") or []),
                "open_ticket_count": len(persona.get("open_tickets") or []),
            },
        )
    if canonical == "get_fd_rates":
        return tool_result(True, "[neutral] FD rates available hain. Main rates compare kar sakti hoon, lekin ek specific FD recommend nahi kar sakti.", {"intent_id": "fd.rates.compare", "rates": DEMO_FD_RATES, "can_recommend_one_fd": False})
    if canonical == "get_support_contact":
        return tool_result(True, "[neutral] Human support 10 AM se 7 PM IST, Monday to Saturday available hai. Contact reference stablemoney dot in slash contact us hai.", dict(SUPPORT_CONTACT))
    if canonical == "send_secure_link":
        link = next((item for item in persona.get("secure_links") or [] if item.get("action") == (args.get("action") or "premature_withdrawal")), None)
        if not link:
            return tool_result(False, "[neutral] Is action ke liye ready secure link available nahi hai.", {"state": "not_found"})
        return tool_result(True, "[neutral] Secure link ready hai.", {**link, "voice_execution_allowed": False})
    if canonical == "create_support_ticket":
        return tool_result(True, "[neutral] Support ticket prepare ho gaya.", {"ticket_id": "TKT-DEMO-00001", "issue": args.get("issue") or "Customer requested support follow-up"})
    return tool_result(False, f"[neutral] Unknown tool {canonical} hai.")

