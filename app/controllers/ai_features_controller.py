"""AI-powered HireHub features: matching blurbs, bid suggest, job gen, deliverable review."""

from __future__ import annotations

import json
import re

from flask import jsonify
from sqlalchemy import func

from app.extensions import db
from app.middleware import is_community_admin
from app.models.ai_match_blurb_model import AiMatchBlurb
from app.models.category_model import Category
from app.models.community_application_model import CommunityApplication
from app.models.community_model import Community
from app.models.contract_model import Contract
from app.models.job_model import Job
from app.models.user_model import User
from app.utils.ai_client import (
    ask_ai,
    check_ai_cooldown,
    cooldown_response,
    mark_ai_call,
)
from app.utils.match_scoring import rank_communities_for_job, rank_jobs_for_community


def _parse_json_object(text: str | None) -> dict | None:
    """Parse a JSON object from model output; None if missing/invalid (treat as AI failure)."""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _get_or_create_blurb(
    job: Job, community: Community, skill_summary: str, *, allow_ai: bool = True
) -> str | None:
    cached = AiMatchBlurb.query.filter_by(job_id=job.id, community_id=community.id).first()
    if cached:
        return cached.blurb
    if not allow_ai:
        return None

    category_name = job.category.name if job.category else "general"
    blurb = ask_ai(
        system_prompt="You write one short sentence explaining why a community fits a job. No fluff.",
        user_prompt=(
            f"Job: {job.title} ({category_name}). {job.description[:280]}\n"
            f"Community: {community.name}. Skills: {skill_summary[:220]}\n"
            "Reply with one sentence only."
        ),
        max_tokens=80,
    )
    if not blurb:
        return None

    blurb = blurb.strip().strip('"')
    row = AiMatchBlurb(job_id=job.id, community_id=community.id, blurb=blurb)
    db.session.add(row)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        existing = AiMatchBlurb.query.filter_by(
            job_id=job.id, community_id=community.id
        ).first()
        return existing.blurb if existing else blurb
    return blurb


def recommended_communities_for_job(job_id: int, user_id: int):
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Unauthorized."}), 401
    if job.posted_by_id != user_id and user.role != "admin":
        return jsonify({"error": "Only the job poster can view recommended communities."}), 403

    ranked = rank_communities_for_job(job, limit=15)
    allow_ai, _ = check_ai_cooldown(user_id, "match_blurb")
    generated = False
    results = []
    for index, (community, meta) in enumerate(ranked):
        item = {
            "community": community.to_dict(include_member_count=True, include_category=True),
            "match_score": meta["match_score"],
            "skill_score": meta["skill_score"],
            "location_match": meta["location_match"],
            "category_match": meta["category_match"],
            "skill_summary": meta["skill_summary"],
            "ai_blurb": None,
            "ai_available": False,
        }
        if index < 3:
            cached = AiMatchBlurb.query.filter_by(
                job_id=job.id, community_id=community.id
            ).first()
            blurb = _get_or_create_blurb(
                job, community, meta["skill_summary"], allow_ai=allow_ai
            )
            if blurb and not cached:
                generated = True
            item["ai_blurb"] = blurb
            item["ai_available"] = blurb is not None
        results.append(item)

    if generated:
        mark_ai_call(user_id, "match_blurb")

    return jsonify({"recommendations": results}), 200


def recommended_jobs_for_community(community_id: int, user_id: int):
    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found."}), 404

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Unauthorized."}), 401
    if not is_community_admin(user_id, community_id) and user.role != "admin":
        return jsonify({"error": "Community admin access required."}), 403

    ranked = rank_jobs_for_community(community, limit=15)
    allow_ai, _ = check_ai_cooldown(user_id, "match_blurb")
    generated = False
    results = []
    for index, (job, meta) in enumerate(ranked):
        item = {
            "job": job.to_dict(include_poster=True, strip_poster=True),
            "match_score": meta["match_score"],
            "skill_score": meta["skill_score"],
            "location_match": meta["location_match"],
            "category_match": meta["category_match"],
            "skill_summary": meta["skill_summary"],
            "ai_blurb": None,
            "ai_available": False,
        }
        if index < 3:
            cached = AiMatchBlurb.query.filter_by(
                job_id=job.id, community_id=community.id
            ).first()
            blurb = _get_or_create_blurb(
                job, community, meta["skill_summary"], allow_ai=allow_ai
            )
            if blurb and not cached:
                generated = True
            item["ai_blurb"] = blurb
            item["ai_available"] = blurb is not None
        results.append(item)

    if generated:
        mark_ai_call(user_id, "match_blurb")

    return jsonify({"recommendations": results}), 200


def _community_bid_stats(community_id: int, category_id: int) -> dict:
    completed = (
        Contract.query.filter_by(community_id=community_id, status="completed")
        .order_by(Contract.created_at.desc())
        .limit(20)
        .all()
    )
    avg_days = None
    avg_price = None
    if completed:
        day_gaps = []
        for contract in completed:
            if contract.created_at and contract.job and contract.job.deadline:
                # Approximate completion span from create → deadline window; prefer payment/created
                created = contract.created_at
                end = contract.created_at
                if hasattr(contract, "payment") and contract.payment and contract.payment.created_at:
                    end = contract.payment.created_at
                delta = (end - created).days
                if delta >= 0:
                    day_gaps.append(max(delta, 1))
        if day_gaps:
            avg_days = round(sum(day_gaps) / len(day_gaps), 1)

    category_apps = (
        db.session.query(func.avg(CommunityApplication.proposed_cost))
        .join(Job, Job.id == CommunityApplication.job_id)
        .filter(
            CommunityApplication.community_id == community_id,
            CommunityApplication.status == "approved",
            Job.category_id == category_id,
        )
        .scalar()
    )
    if category_apps is not None:
        avg_price = round(float(category_apps), 2)
    elif completed:
        same_cat = [
            float(c.total_amount)
            for c in completed
            if c.job and c.job.category_id == category_id and c.total_amount
        ]
        if same_cat:
            avg_price = round(sum(same_cat) / len(same_cat), 2)

    return {
        "completed_contracts": len(completed),
        "average_completion_days": avg_days,
        "average_category_price": avg_price,
    }


def suggest_bid(job_id: int, user_id: int, data: dict):
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.status != "open":
        return jsonify({"error": "Job is not open for bidding."}), 400

    community_id = data.get("community_id")
    try:
        community_id = int(community_id)
    except (TypeError, ValueError):
        return jsonify({"error": "community_id is required."}), 400

    if not is_community_admin(user_id, community_id):
        return jsonify({"error": "Community admin access required."}), 403

    community = Community.query.get(community_id)
    if not community or community.status != "approved":
        return jsonify({"error": "Community not found or not verified."}), 404

    allowed, retry_after = check_ai_cooldown(user_id, "suggest_bid")
    if not allowed:
        return cooldown_response(retry_after)

    stats = _community_bid_stats(community_id, job.category_id)
    category_name = job.category.name if job.category else "General"
    deadline = job.deadline.isoformat() if job.deadline else "unspecified"

    mark_ai_call(user_id, "suggest_bid")
    raw = ask_ai(
        system_prompt=(
            "You suggest a competitive bid for a community job platform. "
            "Reply with a single JSON object only — no markdown, no prose. Schema: "
            '{"suggested_cost": number, "suggested_days": number, "reasoning": "short text"}'
        ),
        user_prompt=(
            f"Job: {job.title}\nCategory: {category_name}\nLocation: {job.location}\n"
            f"Deadline: {deadline}\nClient asking: {float(job.final_price)}\n"
            f"Description: {job.description[:400]}\n"
            f"Community past: completed={stats['completed_contracts']}, "
            f"avg_days={stats['average_completion_days']}, "
            f"avg_category_price={stats['average_category_price']}\n"
            "Return JSON only."
        ),
        max_tokens=200,
    )
    parsed = _parse_json_object(raw)
    if not parsed:
        return jsonify({"error": "AI suggestion unavailable.", "suggestion": None}), 503

    try:
        cost = float(parsed.get("suggested_cost"))
        days = int(float(parsed.get("suggested_days")))
        reasoning = str(parsed.get("reasoning") or "").strip()
    except (TypeError, ValueError):
        return jsonify({"error": "AI suggestion unavailable.", "suggestion": None}), 503

    if cost <= 0 or days <= 0:
        return jsonify({"error": "AI suggestion unavailable.", "suggestion": None}), 503

    return (
        jsonify(
            {
                "suggestion": {
                    "suggested_cost": round(cost, 2),
                    "suggested_days": days,
                    "reasoning": reasoning or "Based on job details and community history.",
                }
            }
        ),
        200,
    )


def generate_job_description(user_id: int, data: dict):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Unauthorized."}), 401

    rough = (data.get("prompt") or data.get("rough_input") or "").strip()
    if not rough:
        return jsonify({"error": "prompt is required."}), 400
    if len(rough) > 1000:
        return jsonify({"error": "prompt is too long (max 1000 chars)."}), 400

    allowed, retry_after = check_ai_cooldown(user_id, "generate_job")
    if not allowed:
        return cooldown_response(retry_after)

    categories = (
        Category.query.filter_by(status="approved")
        .order_by(Category.name.asc())
        .all()
    )
    category_names = [c.name for c in categories]
    names_line = ", ".join(category_names[:40]) if category_names else "General"

    mark_ai_call(user_id, "generate_job")
    raw = ask_ai(
        system_prompt=(
            "You write concise job posts. Reply with a single JSON object only — "
            "no markdown fences, no prose. Schema: "
            '{"title":"...","description":"...","suggested_category":"..."} '
            "Use suggested_category from the provided category list when possible."
        ),
        user_prompt=(
            f"Rough request: {rough}\n"
            f"Categories: {names_line}\n"
            "Return JSON only. Keep description under 120 words."
        ),
        max_tokens=350,
    )
    parsed = _parse_json_object(raw)
    if not parsed:
        return jsonify({"error": "AI suggestion unavailable.", "suggestion": None}), 503

    title = str(parsed.get("title") or "").strip()
    description = str(parsed.get("description") or "").strip()
    suggested_category = str(parsed.get("suggested_category") or "").strip()
    if not title or not description:
        return jsonify({"error": "AI suggestion unavailable.", "suggestion": None}), 503

    category_id = None
    matched_name = None
    if suggested_category:
        lower = suggested_category.lower()
        for cat in categories:
            if cat.name.lower() == lower or lower in cat.name.lower() or cat.name.lower() in lower:
                category_id = cat.id
                matched_name = cat.name
                break

    return (
        jsonify(
            {
                "suggestion": {
                    "title": title[:255],
                    "description": description,
                    "suggested_category": matched_name or suggested_category,
                    "category_id": category_id,
                }
            }
        ),
        200,
    )


def ai_review_deliverable(contract_id: int, user_id: int):
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404

    if not is_community_admin(user_id, contract.community_id):
        user = User.query.get(user_id)
        if not user or user.role != "admin":
            return jsonify({"error": "Community admin access required."}), 403

    if not contract.deliverable_url:
        return jsonify({"error": "No deliverable submitted yet."}), 400

    job = contract.job
    if not job:
        return jsonify({"error": "Job not found for contract."}), 404

    allowed, retry_after = check_ai_cooldown(user_id, "ai_review")
    if not allowed:
        return cooldown_response(retry_after)

    mark_ai_call(user_id, "ai_review")
    review = ask_ai(
        system_prompt=(
            "You assist community admins reviewing deliverables. "
            "Write 3-5 short plain-text sentences: whether the submission seems to match "
            "the job scope, and anything missing or off-scope. Do not approve or reject."
        ),
        user_prompt=(
            f"Job title: {job.title}\n"
            f"Scope: {job.description[:500]}\n"
            f"Deliverable URL/notes: {contract.deliverable_url}\n"
            "Plain text only."
        ),
        max_tokens=250,
    )
    if not review:
        return jsonify({"error": "AI suggestion unavailable.", "review": None}), 503

    return jsonify({"review": review, "assistive": True}), 200


def join_request_fit_analysis(community_id: int, applicant_user_id: int, admin_user_id: int):
    """Compare a pending join applicant's skills to the community's current coverage."""
    from collections import Counter

    from app.models.community_member_model import CommunityMember
    from app.models.skill_model import Skill
    from app.models.user_skill_model import UserSkill

    community = Community.query.get(community_id)
    if not community:
        return jsonify({"available": False, "error": "Community not found."}), 404

    user = User.query.get(admin_user_id)
    if not user:
        return jsonify({"available": False, "error": "Unauthorized."}), 401
    if not is_community_admin(admin_user_id, community_id) and user.role != "admin":
        return jsonify({"available": False, "error": "Community admin access required."}), 403

    pending = CommunityMember.query.filter_by(
        community_id=community_id,
        user_id=applicant_user_id,
        status="pending",
    ).first()
    if not pending:
        return jsonify({"available": False, "error": "Pending join request not found."}), 404

    applicant = User.query.get(applicant_user_id)
    if not applicant:
        return jsonify({"available": False, "error": "Applicant not found."}), 404

    applicant_skills = (
        db.session.query(UserSkill, Skill)
        .join(Skill, Skill.id == UserSkill.skill_id)
        .filter(UserSkill.user_id == applicant_user_id)
        .all()
    )
    applicant_lines = [
        f"{skill.name} ({us.level})" for us, skill in applicant_skills
    ]
    applicant_names = {skill.name for _, skill in applicant_skills}

    approved_member_ids = [
        m.user_id
        for m in CommunityMember.query.filter_by(
            community_id=community_id, status="approved"
        ).all()
    ]
    coverage: Counter[str] = Counter()
    if approved_member_ids:
        rows = (
            db.session.query(Skill.name, func.count(func.distinct(UserSkill.user_id)))
            .join(UserSkill, UserSkill.skill_id == Skill.id)
            .filter(UserSkill.user_id.in_(approved_member_ids))
            .group_by(Skill.name)
            .all()
        )
        for name, count in rows:
            coverage[name] = int(count)

    community_skill_names = set(coverage.keys())
    coverage_lines = [
        f"{name} ({count} member{'s' if count != 1 else ''})"
        for name, count in coverage.most_common(20)
    ]

    # Deterministic overlap/new sets (AI may refine labels; we prefer these for tags)
    overlap_skills = sorted(applicant_names & community_skill_names)
    new_skills_added = sorted(applicant_names - community_skill_names)

    allowed, retry_after = check_ai_cooldown(admin_user_id, "fit_analysis")
    if not allowed:
        body, status = cooldown_response(retry_after)
        # Keep fit-analysis shape for the UI
        payload = body.get_json()
        payload["analysis"] = None
        return jsonify(payload), status

    mark_ai_call(admin_user_id, "fit_analysis")
    raw = ask_ai(
        system_prompt=(
            "You help community admins review join requests. "
            "Reply with a single JSON object only — no markdown. Schema: "
            '{"fit_summary":"1-2 sentences","overlap_skills":["..."],"new_skills_added":["..."]}'
        ),
        user_prompt=(
            f"Community: {community.name}\n"
            f"Applicant: {applicant.full_name}\n"
            f"Applicant skills: {', '.join(applicant_lines) or 'none listed'}\n"
            f"Community skill coverage: {', '.join(coverage_lines) or 'none yet'}\n"
            "overlap = skills applicant shares with existing members; "
            "new = skills applicant adds that the community lacks. JSON only."
        ),
        max_tokens=220,
    )
    parsed = _parse_json_object(raw)
    if not parsed:
        return (
            jsonify(
                {
                    "available": False,
                    "analysis": None,
                    "error": "AI suggestion unavailable.",
                }
            ),
            200,
        )

    fit_summary = str(parsed.get("fit_summary") or "").strip()
    if not fit_summary:
        return (
            jsonify(
                {
                    "available": False,
                    "analysis": None,
                    "error": "AI suggestion unavailable.",
                }
            ),
            200,
        )

    # Prefer Claude lists when present and non-empty; otherwise fall back to computed sets
    ai_overlap = parsed.get("overlap_skills")
    ai_new = parsed.get("new_skills_added")
    if isinstance(ai_overlap, list) and ai_overlap:
        overlap_skills = [str(s).strip() for s in ai_overlap if str(s).strip()]
    if isinstance(ai_new, list) and ai_new:
        new_skills_added = [str(s).strip() for s in ai_new if str(s).strip()]

    return (
        jsonify(
            {
                "available": True,
                "analysis": {
                    "fit_summary": fit_summary,
                    "overlap_skills": overlap_skills,
                    "new_skills_added": new_skills_added,
                },
                "assistive": True,
            }
        ),
        200,
    )


def _report_context_block(report) -> str:
    lines = [
        f"Report reason: {report.reason}",
        f"Report status: {report.status}",
        f"Target: {report.target_type} #{report.target_id}",
    ]
    if report.reporter:
        lines.append(f"Reporter: {report.reporter.full_name}")

    if report.description:
        lines.append(f"Description: {report.description}")
    if report.evidence_url:
        lines.append(f"Evidence: {report.evidence_url}")
    return "\n".join(lines)


def summarize_dispute(report_id: int, user_id: int):
    """Platform-admin AI summary of a report/dispute — display only, never auto-acts."""
    from app.models.report_model import Report

    user = User.query.get(user_id)
    if not user or user.role != "admin":
        return jsonify({"error": "Platform admin access required.", "summary": None}), 403

    report = Report.query.get(report_id)
    if not report:
        return jsonify({"error": "Report not found.", "summary": None}), 404

    allowed, retry_after = check_ai_cooldown(user_id, "dispute_summary")
    if not allowed:
        return cooldown_response(retry_after)

    mark_ai_call(user_id, "dispute_summary")
    raw = ask_ai(
        system_prompt=(
            "You summarize platform disputes for moderators. "
            "Reply with a single JSON object only — no markdown. Schema: "
            '{"summary":"3-5 neutral sentences","suggested_direction":"1-2 sentences as an option"}. '
            "No blame language. Never issue a directive — frame direction as something to consider."
        ),
        user_prompt=_report_context_block(report) + "\nReturn JSON only.",
        max_tokens=350,
    )
    parsed = _parse_json_object(raw)
    if not parsed:
        return jsonify({"error": "AI summary unavailable.", "summary": None}), 503

    summary = str(parsed.get("summary") or "").strip()
    direction = str(parsed.get("suggested_direction") or "").strip()
    if not summary:
        return jsonify({"error": "AI summary unavailable.", "summary": None}), 503

    return (
        jsonify(
            {
                "summary": summary,
                "suggested_direction": direction or None,
                "assistive": True,
            }
        ),
        200,
    )


def generate_open_call_description(user_id: int, data: dict):
    """AI recruiting copy for community open calls — draft only, never auto-posts."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Unauthorized.", "suggestion": None}), 401

    rough = (data.get("prompt") or data.get("rough_input") or data.get("title") or "").strip()
    if not rough:
        return jsonify({"error": "title or prompt is required.", "suggestion": None}), 400

    skills = data.get("required_skills") or data.get("skills") or []
    if isinstance(skills, list):
        skills_line = ", ".join(str(s).strip() for s in skills if str(s).strip())
    else:
        skills_line = str(skills).strip()

    allowed, retry_after = check_ai_cooldown(user_id, "open_call_description")
    if not allowed:
        return cooldown_response(retry_after)

    mark_ai_call(user_id, "open_call_description")
    raw = ask_ai(
        system_prompt=(
            "You write short recruiting copy for a skilled community open call. "
            "Tone: inviting team recruitment (e.g. we're looking for a React developer to join), "
            "not client job posting. Reply with a single JSON object only — no markdown. Schema: "
            '{"description":"..."} Keep under 100 words.'
        ),
        user_prompt=(
            f"Open call title/prompt: {rough}\n"
            f"Required skills: {skills_line or 'not specified'}\n"
            "Return JSON only."
        ),
        max_tokens=280,
    )
    parsed = _parse_json_object(raw)
    if not parsed:
        return jsonify({"error": "AI suggestion unavailable.", "suggestion": None}), 503

    description = str(parsed.get("description") or "").strip()
    if not description:
        return jsonify({"error": "AI suggestion unavailable.", "suggestion": None}), 503

    return jsonify({"suggestion": {"description": description}, "assistive": True}), 200


def get_community_review_digest(community_id: int):
    from app.utils.review_digest_utils import get_review_digest

    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found."}), 404
    return jsonify({"digest": get_review_digest(community_id)}), 200
