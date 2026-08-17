"""Algorithmic job ↔ community match scoring (no LLM)."""

from __future__ import annotations

from sqlalchemy import func

from app.extensions import db
from app.models.community_member_model import CommunityMember
from app.models.community_model import Community
from app.models.job_model import Job
from app.models.review_model import Review
from app.models.skill_model import Skill
from app.models.user_skill_model import UserSkill

_LEVEL_WEIGHT = {
    "beginner": 0.25,
    "intermediate": 0.5,
    "advanced": 0.75,
    "expert": 1.0,
}

_LOCATION_BONUS = 15.0
_CATEGORY_BONUS = 10.0


def _norm_loc(value: str | None) -> str:
    return (value or "").strip().lower()


def _member_avg_ratings(user_ids: list[int]) -> dict[int, float]:
    if not user_ids:
        return {}
    rows = (
        db.session.query(Review.member_id, func.avg(Review.rating))
        .filter(Review.member_id.in_(user_ids))
        .group_by(Review.member_id)
        .all()
    )
    return {uid: float(avg) for uid, avg in rows if uid is not None and avg is not None}


def _community_skill_summary(community: Community, member_ids: list[int]) -> str:
    if not member_ids:
        return "No approved members yet."
    skills = (
        db.session.query(Skill.name, UserSkill.level, func.count(UserSkill.id))
        .join(UserSkill, UserSkill.skill_id == Skill.id)
        .filter(UserSkill.user_id.in_(member_ids))
        .group_by(Skill.name, UserSkill.level)
        .order_by(func.count(UserSkill.id).desc())
        .limit(12)
        .all()
    )
    if not skills:
        parts = []
        if community.specialization:
            parts.append(f"Specialization: {community.specialization}")
        if community.category:
            parts.append(f"Category: {community.category.name}")
        return "; ".join(parts) or "Limited skill data."
    return ", ".join(f"{name} ({level}×{count})" for name, level, count in skills)


def score_community_for_job(job: Job, community: Community) -> dict:
    """Return match_score (0–100), skill_score, location_match, and skill_summary."""
    category_name = (job.category.name if job.category else "").strip().lower()

    members = CommunityMember.query.filter_by(
        community_id=community.id, status="approved"
    ).all()
    member_ids = [m.user_id for m in members]
    member_count = len(member_ids) or 1
    ratings = _member_avg_ratings(member_ids)

    # Skills whose Skill.category matches the job category name, or community shares category_id
    matching_skills = []
    if member_ids and category_name:
        matching_skills = (
            db.session.query(UserSkill)
            .join(Skill, Skill.id == UserSkill.skill_id)
            .filter(
                UserSkill.user_id.in_(member_ids),
                func.lower(Skill.category) == category_name,
            )
            .all()
        )

    # Also treat same category_id as a soft match signal via any skill on those members
    members_with_match = set()
    weighted = 0.0
    for us in matching_skills:
        level_w = _LEVEL_WEIGHT.get(us.level, 0.5)
        rating = ratings.get(us.user_id, 3.0)  # default mid rating if none
        rating_w = max(0.2, min(1.0, rating / 5.0))
        weighted += level_w * rating_w
        members_with_match.add(us.user_id)

    # Fallback: if community category matches job category, give baseline overlap
    category_match = bool(
        community.category_id and job.category_id and community.category_id == job.category_id
    )
    if not matching_skills and category_match:
        # Use community reputation / experience as weak signal across members
        for uid in member_ids:
            rating = ratings.get(uid, 3.0)
            weighted += 0.35 * max(0.2, min(1.0, rating / 5.0))
            members_with_match.add(uid)

    coverage = len(members_with_match) / member_count
    avg_weight = (weighted / len(matching_skills)) if matching_skills else (weighted / member_count if category_match else 0.0)
    skill_score = round(min(100.0, coverage * 70.0 + avg_weight * 30.0), 1)

    location_match = _norm_loc(community.location) == _norm_loc(job.location) and bool(
        _norm_loc(job.location)
    )
    location_bonus = _LOCATION_BONUS if location_match else 0.0
    category_bonus = _CATEGORY_BONUS if category_match else 0.0

    match_score = round(min(100.0, skill_score + location_bonus + category_bonus), 1)

    return {
        "match_score": match_score,
        "skill_score": skill_score,
        "location_match": location_match,
        "category_match": category_match,
        "skill_summary": _community_skill_summary(community, member_ids),
        "member_count": len(member_ids),
    }


def rank_communities_for_job(job: Job, limit: int = 20) -> list[tuple[Community, dict]]:
    communities = Community.query.filter_by(status="approved").all()
    scored = []
    for community in communities:
        meta = score_community_for_job(job, community)
        if meta["match_score"] <= 0 and not meta["category_match"] and not meta["location_match"]:
            continue
        scored.append((community, meta))
    scored.sort(key=lambda item: item[1]["match_score"], reverse=True)
    return scored[:limit]


def rank_jobs_for_community(community: Community, limit: int = 20) -> list[tuple[Job, dict]]:
    jobs = Job.query.filter_by(status="open").all()
    scored = []
    for job in jobs:
        meta = score_community_for_job(job, community)
        if meta["match_score"] <= 0 and not meta["category_match"] and not meta["location_match"]:
            continue
        scored.append((job, meta))
    scored.sort(key=lambda item: item[1]["match_score"], reverse=True)
    return scored[:limit]
