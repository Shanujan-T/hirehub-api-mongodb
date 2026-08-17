"""Weekly AI digest for community admins — run via CLI or optional scheduler."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func

from app.extensions import db
from app.models.community_model import Community
from app.models.contract_application_model import ContractApplication
from app.models.contract_model import Contract
from app.models.job_model import Job
from app.models.payment_model import Payment
from app.utils import utc_now
from app.utils.ai_client import ask_ai
from app.utils.notification_utils import notify_community_admins

logger = logging.getLogger(__name__)


def _week_window():
    end = utc_now()
    start = end - timedelta(days=7)
    return start, end


def _digest_stats(community: Community) -> dict:
    start, end = _week_window()
    category_id = community.category_id

    matching_jobs = 0
    if category_id:
        matching_jobs = (
            Job.query.filter(
                Job.status == "open",
                Job.category_id == category_id,
                Job.created_at >= start,
                Job.created_at <= end,
            ).count()
        )

    pending_applicants = (
        db.session.query(func.count(ContractApplication.id))
        .join(Contract, Contract.id == ContractApplication.contract_id)
        .filter(
            Contract.community_id == community.id,
            Contract.status == "open_internally",
            ContractApplication.status == "applied",
        )
        .scalar()
    ) or 0

    commission = (
        db.session.query(func.coalesce(func.sum(Payment.commission_amount), 0))
        .join(Contract, Contract.id == Payment.contract_id)
        .filter(
            Contract.community_id == community.id,
            Payment.status == "released",
            Payment.released_at >= start,
            Payment.released_at <= end,
        )
        .scalar()
    )
    try:
        commission_total = float(commission or 0)
    except (TypeError, ValueError):
        commission_total = 0.0

    return {
        "matching_jobs": int(matching_jobs),
        "pending_applicants": int(pending_applicants),
        "commission_total": round(commission_total, 2),
        "community_name": community.name,
    }


def generate_weekly_digest_text(community: Community) -> str | None:
    stats = _digest_stats(community)
    raw = ask_ai(
        system_prompt=(
            "You write a brief weekly update for a community admin on a hiring platform. "
            "2-3 plain sentences. Friendly, factual, no hype. Do not invent numbers."
        ),
        user_prompt=(
            f"Community: {stats['community_name']}\n"
            f"New open jobs matching category this week: {stats['matching_jobs']}\n"
            f"Pending contract applicants awaiting selection: {stats['pending_applicants']}\n"
            f"Commission earned this week (USD): {stats['commission_total']}\n"
            "Write the digest paragraph only."
        ),
        max_tokens=180,
    )
    if raw:
        return raw.strip()

    # Deterministic fallback so the weekly job still notifies when AI is down
    return (
        f"{stats['matching_jobs']} new job(s) matched your category this week, "
        f"{stats['pending_applicants']} applicant(s) are waiting on your review, "
        f"and you earned ${stats['commission_total']:.2f} in commission."
    )


def run_weekly_digests() -> int:
    """Create weekly_digest notifications for admins of every approved community."""
    communities = Community.query.filter_by(status="approved").all()
    sent = 0
    for community in communities:
        try:
            body = generate_weekly_digest_text(community)
            if not body:
                continue
            notify_community_admins(
                community.id,
                notification_type="weekly_digest",
                title="Your weekly community digest",
                body=body,
                link_href="/community-admin/dashboard",
            )
            sent += 1
        except Exception:
            logger.exception("weekly digest failed for community_id=%s", community.id)
    logger.info("weekly digests sent for %s communities", sent)
    return sent
