"""Contract health risk scoring (algorithmic + optional AI reason)."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.extensions import db
from app.models.contract_model import Contract
from app.models.message_model import Message
from app.utils import utc_now
from app.utils.ai_client import ask_ai

logger = logging.getLogger(__name__)

# Statuses monitored for health (per product scope).
MONITORED_STATUSES = ("open_internally", "active", "submitted")
# Statuses where deliverable/deadline urgency no longer applies the same way.
POST_SUBMIT_STATUSES = ("submitted", "completed")

DEADLINE_PROXIMITY_DAYS = 3
DELIVERABLE_URGENCY_DAYS = 2
MESSAGE_SILENCE_DAYS = 5


def _days_until_deadline(job) -> int | None:
    if not job or not job.deadline:
        return None
    deadline = job.deadline
    if hasattr(deadline, "date"):
        deadline = deadline.date()
    today = utc_now().date() if hasattr(utc_now(), "date") else date.today()
    # utc_now returns naive datetime
    today = date.today()
    return (deadline - today).days


def _last_message_at(contract: Contract):
    conversation = contract.conversation
    if not conversation:
        return None
    last = (
        Message.query.filter_by(conversation_id=conversation.id, deleted_for_everyone=False)
        .order_by(Message.created_at.desc())
        .first()
    )
    return last.created_at if last else None


def collect_risk_flags(contract: Contract) -> list[str]:
    """Return algorithmic risk flag codes for a contract."""
    if contract.status not in MONITORED_STATUSES:
        return []

    flags: list[str] = []
    days_left = _days_until_deadline(contract.job)

    # Deadline proximity: within 3 days and not yet submitted/completed
    if (
        days_left is not None
        and days_left <= DEADLINE_PROXIMITY_DAYS
        and contract.status not in POST_SUBMIT_STATUSES
    ):
        flags.append("deadline_proximity")

    # Message silence: no message in 5+ days while still in progress
    if contract.status in ("open_internally", "active"):
        last_at = _last_message_at(contract)
        now = utc_now()
        if last_at is None:
            # Conversation exists but empty, or never messaged — silence if contract is older than threshold
            created = contract.created_at or now
            if (now - created).days >= MESSAGE_SILENCE_DAYS:
                flags.append("message_silence")
        else:
            if (now - last_at).days >= MESSAGE_SILENCE_DAYS:
                flags.append("message_silence")

    # No deliverable with less than 2 days to deadline
    if (
        days_left is not None
        and days_left < DELIVERABLE_URGENCY_DAYS
        and contract.status not in POST_SUBMIT_STATUSES
        and not (contract.deliverable_url or "").strip()
    ):
        flags.append("no_deliverable")

    return flags


def _level_from_flags(flags: list[str]) -> str:
    if not flags:
        return "none"
    if len(flags) >= 2 or "no_deliverable" in flags:
        return "high"
    return "low"


def _algorithmic_reason(contract: Contract, flags: list[str]) -> str:
    days_left = _days_until_deadline(contract.job)
    parts: list[str] = []
    if "deadline_proximity" in flags:
        if days_left is not None and days_left <= 0:
            parts.append("Deadline has passed or is today")
        elif days_left is not None:
            parts.append(f"Deadline in {days_left} day{'s' if days_left != 1 else ''}")
        else:
            parts.append("Deadline approaching")
    if "message_silence" in flags:
        parts.append("no recent communication")
    if "no_deliverable" in flags:
        parts.append("no deliverable submitted")
    if not parts:
        return "Needs attention"
    if len(parts) == 1:
        return parts[0][0].upper() + parts[0][1:]
    return f"{parts[0][0].upper() + parts[0][1:]} with {parts[1]}" + (
        f" and {parts[2]}" if len(parts) > 2 else ""
    )


def _ai_reason(contract: Contract, flags: list[str]) -> str | None:
    job_title = contract.job.title if contract.job else f"Contract #{contract.id}"
    days_left = _days_until_deadline(contract.job)
    prompt = (
        f"Contract for job '{job_title}', status={contract.status}, "
        f"days_until_deadline={days_left}, flags={', '.join(flags)}. "
        "Write ONE short sentence explaining why this contract needs attention. "
        "No quotes, no preamble."
    )
    return ask_ai(
        system_prompt="You write brief contract-risk alerts for a freelance marketplace.",
        user_prompt=prompt,
        max_tokens=60,
    )


def score_contract(contract: Contract, *, with_ai: bool = False) -> Contract:
    """Update risk_level / risk_reason on the contract (caller commits)."""
    flags = collect_risk_flags(contract)
    level = _level_from_flags(flags)
    previous_level = contract.risk_level
    previous_reason = contract.risk_reason

    contract.risk_level = level
    contract.risk_flags = ",".join(flags) if flags else None
    contract.risk_checked_at = utc_now()

    if level == "none":
        contract.risk_reason = None
    elif with_ai and level == "high" and (not previous_reason or previous_level != "high"):
        ai_text = _ai_reason(contract, flags)
        contract.risk_reason = (ai_text or _algorithmic_reason(contract, flags)).strip()
    elif not contract.risk_reason or previous_level != level:
        # Refresh cached reason when level changes; keep AI reason if still high
        if level == "high" and previous_reason and previous_level == "high" and not with_ai:
            pass  # keep cached AI reason
        else:
            contract.risk_reason = _algorithmic_reason(contract, flags)

    return contract


def run_contract_health_scan(*, with_ai: bool = True) -> dict:
    """Score all monitored contracts. Optionally generate AI reasons for high risk."""
    contracts = Contract.query.filter(Contract.status.in_(MONITORED_STATUSES)).all()
    high = low = none = 0
    for contract in contracts:
        score_contract(contract, with_ai=with_ai)
        if contract.risk_level == "high":
            high += 1
        elif contract.risk_level == "low":
            low += 1
        else:
            none += 1
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("contract health scan commit failed")
        raise
    return {"scanned": len(contracts), "high": high, "low": low, "none": none}


def ensure_fresh_scores(contracts: list[Contract], *, max_age_hours: float = 1.0) -> None:
    """Recompute algorithmic scores if stale (no AI)."""
    now = utc_now()
    dirty = False
    for contract in contracts:
        if contract.status not in MONITORED_STATUSES:
            if contract.risk_level and contract.risk_level != "none":
                contract.risk_level = "none"
                contract.risk_reason = None
                contract.risk_flags = None
                dirty = True
            continue
        checked = contract.risk_checked_at
        stale = checked is None or (now - checked) > timedelta(hours=max_age_hours)
        if stale:
            score_contract(contract, with_ai=False)
            dirty = True
    if dirty:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("ensure_fresh_scores commit failed")
