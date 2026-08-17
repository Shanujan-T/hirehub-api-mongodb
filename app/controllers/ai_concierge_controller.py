"""AI Community Concierge — intent-routed, user-scoped data only (no free-form SQL)."""

from __future__ import annotations

from datetime import datetime

from flask import jsonify
from sqlalchemy import func, or_

from app.extensions import db
from app.middleware import get_admin_community_ids
from app.models.community_member_model import CommunityMember
from app.models.community_model import Community
from app.models.contract_model import Contract
from app.models.job_model import Job
from app.models.payment_model import Payment
from app.models.review_model import Review
from app.models.skill_model import Skill
from app.models.user_model import User
from app.models.user_skill_model import UserSkill
from app.utils import utc_now
from app.utils.ai_client import ask_ai, check_ai_cooldown, is_ai_configured, mark_ai_call

FALLBACK_MESSAGE = (
    "I can help with: your jobs, your communities, your earnings, your contracts, "
    "or your team's skills. Try asking something like "
    '"What jobs have I posted?" or "Who on my team has the most experience?"'
)

_SUGGESTED = [
    "What jobs is my community eligible for?",
    "Who on my team has the most experience?",
    "How much have I earned this month?",
]


def _classify_intent(question: str) -> str:
    q = (question or "").strip().lower()
    if not q:
        return "unrecognized"

    if any(k in q for k in ("earn", "payment", "payout", "commission", "income", "paid")):
        return "my_earnings"
    if any(
        k in q
        for k in (
            "team skill",
            "who on my team",
            "member skill",
            "experience",
            "skills in my",
            "most experience",
        )
    ):
        return "team_skills"
    if any(k in q for k in ("contract", "deliverable", "assignment")):
        return "my_contracts"
    if any(k in q for k in ("community", "communities", "membership")):
        return "my_communities"
    if any(k in q for k in ("job", "posting", "eligible", "marketplace", "bid")):
        return "my_jobs"
    return "unrecognized"


def _scoped_my_jobs(user_id: int) -> dict:
    jobs = (
        Job.query.filter_by(posted_by_id=user_id)
        .order_by(Job.created_at.desc())
        .limit(20)
        .all()
    )
    payload: dict = {
        "jobs_posted": [
            {
                "id": j.id,
                "title": j.title,
                "status": j.status,
                "location": j.location,
                "final_price": float(j.final_price) if j.final_price is not None else None,
                "category": j.category.name if j.category else None,
            }
            for j in jobs
        ],
        "count": len(jobs),
    }

    # Community admins: include top open-job matches for their communities
    from app.utils.match_scoring import rank_jobs_for_community

    admin_ids = get_admin_community_ids(user_id)
    eligible = []
    for community_id in admin_ids[:2]:
        community = Community.query.get(community_id)
        if not community:
            continue
        ranked = rank_jobs_for_community(community, limit=8)
        eligible.append(
            {
                "community_id": community_id,
                "community_name": community.name,
                "recommended_open_jobs": [
                    {
                        "id": job.id,
                        "title": job.title,
                        "location": job.location,
                        "match_score": meta["match_score"],
                        "skill_summary": meta["skill_summary"],
                    }
                    for job, meta in ranked
                ],
            }
        )
    if eligible:
        payload["community_eligible_jobs"] = eligible
    return payload


def _scoped_my_communities(user_id: int) -> dict:
    memberships = (
        CommunityMember.query.filter_by(user_id=user_id)
        .order_by(CommunityMember.id.desc())
        .limit(30)
        .all()
    )
    rows = []
    for m in memberships:
        community = m.community
        rows.append(
            {
                "community_id": m.community_id,
                "name": community.name if community else None,
                "role": m.role,
                "status": m.status,
                "community_status": community.status if community else None,
                "location": community.location if community else None,
            }
        )
    return {"memberships": rows, "count": len(rows)}


def _scoped_my_earnings(user_id: int) -> dict:
    now = utc_now()
    month_start = datetime(now.year, now.month, 1)

    member_payments = (
        Payment.query.join(Contract)
        .filter(Contract.assigned_member_id == user_id, Payment.status == "released")
        .all()
    )
    admin_ids = get_admin_community_ids(user_id)
    admin_payments = []
    if admin_ids:
        admin_payments = (
            Payment.query.join(Contract)
            .filter(Contract.community_id.in_(admin_ids), Payment.status == "released")
            .all()
        )

    def _sum(payments, field: str, since=None) -> float:
        total = 0.0
        for p in payments:
            if since and (not p.released_at or p.released_at < since):
                continue
            value = getattr(p, field, None)
            if value is not None:
                total += float(value)
        return round(total, 2)

    return {
        "member_payout_total": _sum(member_payments, "member_payout"),
        "member_payout_this_month": _sum(member_payments, "member_payout", month_start),
        "admin_commission_total": _sum(admin_payments, "commission_amount"),
        "admin_commission_this_month": _sum(admin_payments, "commission_amount", month_start),
        "released_payment_count": len({p.id for p in member_payments + admin_payments}),
    }


def _scoped_my_contracts(user_id: int) -> dict:
    admin_ids = get_admin_community_ids(user_id)
    filters = [Contract.assigned_member_id == user_id]
    if admin_ids:
        filters.append(Contract.community_id.in_(admin_ids))
    posted_job_ids = [j.id for j in Job.query.filter_by(posted_by_id=user_id).all()]
    if posted_job_ids:
        filters.append(Contract.job_id.in_(posted_job_ids))

    contracts = (
        Contract.query.filter(or_(*filters))
        .order_by(Contract.created_at.desc())
        .limit(25)
        .all()
    )
    return {
        "contracts": [
            {
                "id": c.id,
                "status": c.status,
                "job_title": c.job.title if c.job else None,
                "community_id": c.community_id,
                "total_amount": float(c.total_amount) if c.total_amount is not None else None,
                "assigned_member_id": c.assigned_member_id,
            }
            for c in contracts
        ],
        "count": len(contracts),
    }


def _scoped_team_skills(user_id: int) -> dict:
    admin_ids = get_admin_community_ids(user_id)
    if not admin_ids:
        membership = (
            CommunityMember.query.filter_by(user_id=user_id, status="approved")
            .order_by(CommunityMember.id.asc())
            .first()
        )
        if membership:
            admin_ids = [membership.community_id]
    if not admin_ids:
        return {"communities": [], "note": "You are not in an approved community yet."}

    communities_payload = []
    for community_id in admin_ids[:3]:
        community = Community.query.get(community_id)
        members = CommunityMember.query.filter_by(
            community_id=community_id, status="approved"
        ).all()
        member_ids = [m.user_id for m in members]
        skill_rows = []
        if member_ids:
            rating_subq = (
                db.session.query(Review.member_id, func.avg(Review.rating).label("avg_rating"))
                .group_by(Review.member_id)
                .subquery()
            )
            skill_rows = (
                db.session.query(
                    User.full_name,
                    Skill.name,
                    UserSkill.level,
                    rating_subq.c.avg_rating,
                )
                .select_from(UserSkill)
                .join(User, User.id == UserSkill.user_id)
                .join(Skill, Skill.id == UserSkill.skill_id)
                .outerjoin(rating_subq, rating_subq.c.member_id == User.id)
                .filter(UserSkill.user_id.in_(member_ids))
                .order_by(User.full_name.asc(), Skill.name.asc())
                .limit(80)
                .all()
            )
        communities_payload.append(
            {
                "community_id": community_id,
                "name": community.name if community else None,
                "member_count": len(member_ids),
                "skills": [
                    {
                        "member": row[0],
                        "skill": row[1],
                        "level": row[2],
                        "avg_rating": float(row[3]) if row[3] is not None else None,
                    }
                    for row in skill_rows
                ],
            }
        )
    return {"communities": communities_payload}


_FETCHERS = {
    "my_jobs": _scoped_my_jobs,
    "my_communities": _scoped_my_communities,
    "my_earnings": _scoped_my_earnings,
    "my_contracts": _scoped_my_contracts,
    "team_skills": _scoped_team_skills,
}


def ask_concierge(user_id: int, data: dict):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Unauthorized."}), 401

    question = (data.get("question") or data.get("message") or "").strip()
    if not question:
        return jsonify({"error": "question is required."}), 400
    if len(question) > 500:
        return jsonify({"error": "question is too long (max 500 chars)."}), 400

    api_configured = is_ai_configured()
    if not api_configured:
        return (
            jsonify(
                {
                    "answer": None,
                    "intent": None,
                    "available": False,
                    "configured": False,
                    "message": "AI assistant is not configured.",
                    "suggested_prompts": _SUGGESTED,
                }
            ),
            200,
        )

    allowed, retry_after = check_ai_cooldown(user_id, "concierge")
    if not allowed:
        return (
            jsonify(
                {
                    "answer": None,
                    "intent": None,
                    "available": False,
                    "configured": True,
                    "message": f"AI assistant is cooling down — try again in {retry_after}s.",
                    "retry_after": retry_after,
                    "suggested_prompts": _SUGGESTED,
                }
            ),
            200,
        )

    intent = _classify_intent(question)
    if intent == "unrecognized":
        return (
            jsonify(
                {
                    "answer": FALLBACK_MESSAGE,
                    "intent": "unrecognized",
                    "available": True,
                    "configured": True,
                    "suggested_prompts": _SUGGESTED,
                }
            ),
            200,
        )

    scoped = _FETCHERS[intent](user_id)
    mark_ai_call(user_id, "concierge")
    answer = ask_ai(
        system_prompt=(
            "You are HireHub's community concierge. Answer the user's question using ONLY "
            "the JSON data provided. Be concise (2-5 sentences). If the data is empty, say so. "
            "Never invent records or claim access to other users' private data."
        ),
        user_prompt=(
            f"User question: {question}\n"
            f"Intent: {intent}\n"
            f"Scoped data JSON: {scoped}\n"
            "Answer in plain language."
        ),
        max_tokens=280,
    )
    if not answer:
        return (
            jsonify(
                {
                    "answer": None,
                    "intent": intent,
                    "available": False,
                    "configured": True,
                    "message": "AI assistant is temporarily unavailable.",
                    "suggested_prompts": _SUGGESTED,
                }
            ),
            200,
        )

    return (
        jsonify(
            {
                "answer": answer.strip(),
                "intent": intent,
                "available": True,
                "configured": True,
                "assistive": True,
                "suggested_prompts": _SUGGESTED,
            }
        ),
        200,
    )


def concierge_meta():
    configured = is_ai_configured()
    return (
        jsonify(
            {
                "configured": configured,
                "available": configured,
                "suggested_prompts": _SUGGESTED,
                "message": None if configured else "AI assistant is not configured.",
            }
        ),
        200,
    )
