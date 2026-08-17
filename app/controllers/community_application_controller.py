import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import jsonify

from app.extensions import db
from app.middleware import (
    can_browse_job_marketplace,
    community_meets_minimum,
    get_admin_community_ids,
    is_community_admin,
)
from app.models.community_application_model import CommunityApplication
from app.models.community_member_model import CommunityMember
from app.models.community_model import Community
from app.models.contract_model import Contract
from app.models.conversation_model import Conversation
from app.models.job_model import Job
from app.utils.notification_utils import (
    notify_community_admins,
    notify_job_application_approved,
    notify_job_application_rejected,
)

logger = logging.getLogger(__name__)

MIN_COMMUNITY_MEMBERS = 3


def _validate_commission_percent(percent):
    if percent is None:
        return Decimal("3.0")
    pct = Decimal(str(percent))
    if pct < Decimal("2") or pct > Decimal("5"):
        return None
    return pct


def _validate_bid(data):
    proposed_cost = (data or {}).get("proposed_cost")
    proposed_days = (data or {}).get("proposed_days")
    if proposed_cost is None or proposed_days is None:
        return None, (jsonify({"errors": ["proposed_cost and proposed_days are required."]}), 400)
    try:
        cost = Decimal(str(proposed_cost))
        days = int(proposed_days)
    except (InvalidOperation, ValueError, TypeError):
        return None, (jsonify({"errors": ["proposed_cost and proposed_days must be valid numbers."]}), 400)
    if cost <= 0 or days <= 0:
        return None, (jsonify({"errors": ["proposed_cost and proposed_days must be greater than 0."]}), 400)
    note = (data or {}).get("note")
    if note is not None:
        note = str(note).strip() or None
    return (cost, days, note), None


def _days_until_deadline(job) -> int:
    if not job or not job.deadline:
        return 7
    deadline = job.deadline
    if hasattr(deadline, "date"):
        deadline = deadline.date()
    return max(1, (deadline - date.today()).days)


def apply_to_job(job_id, community_id, user_id, data=None):
    if not can_browse_job_marketplace(user_id):
        return (
            jsonify(
                {
                    "error": "Job marketplace is available only to community admins "
                    "of verified communities with at least 3 approved members."
                }
            ),
            403,
        )

    bid, error = _validate_bid(data)
    if error:
        return error
    proposed_cost, proposed_days, note = bid

    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.status != "open":
        return jsonify({"error": "Job is not open for applications."}), 400
    if not is_community_admin(user_id, community_id):
        return jsonify({"error": "Forbidden."}), 403

    community = Community.query.get(community_id)
    if not community or community.status != "approved":
        return jsonify({"error": "Community must be approved before applying to jobs."}), 403

    if not community_meets_minimum(community_id):
        return jsonify({"error": f"Community must have at least {MIN_COMMUNITY_MEMBERS} approved members."}), 400

    if community.category_id != job.category_id:
        return jsonify({"error": "Community category must match the job category."}), 400

    existing = CommunityApplication.query.filter_by(
        job_id=job_id, community_id=community_id
    ).first()
    if existing:
        return jsonify({"error": "Community already applied to this job."}), 409

    application = CommunityApplication(
        job_id=job_id,
        community_id=community_id,
        status="applied",
        source="applied",
        proposed_cost=proposed_cost,
        proposed_days=proposed_days,
        note=note,
    )
    db.session.add(application)
    try:
        db.session.commit()
        return jsonify({
            "message": "Applied to job.",
            "community_application": application.to_dict(include_community=True),
        }), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to apply to job."}), 500


def invite_community_to_job(job_id, community_id, employer_id):
    """A job-posting user invites a community (same CommunityApplication pipeline)."""
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.posted_by_id != int(employer_id):
        return jsonify({"error": "Forbidden."}), 403
    if job.status != "open":
        return jsonify({"error": "Job is not open for invitations."}), 400

    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found."}), 404
    if community.status != "approved":
        return jsonify({"error": "Community must be approved before it can be invited."}), 400
    if community.category_id != job.category_id:
        return jsonify({
            "error": "Community category must match the job category. "
            "Invite only communities in the same category as this job."
        }), 400
    if not community_meets_minimum(community_id):
        return jsonify({
            "error": f"Community must have at least {MIN_COMMUNITY_MEMBERS} approved members."
        }), 400

    existing = CommunityApplication.query.filter_by(
        job_id=job_id, community_id=community_id
    ).first()
    if existing:
        if existing.source == "invited":
            return jsonify({"error": "This community has already been invited to this job."}), 409
        return jsonify({"error": "This community has already applied to this job."}), 409

    application = CommunityApplication(
        job_id=job_id,
        community_id=community_id,
        status="applied",
        source="invited",
        proposed_cost=job.final_price,
        proposed_days=_days_until_deadline(job),
        note=None,
    )
    db.session.add(application)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to invite community."}), 500

    try:
        notify_community_admins(
            community_id,
            notification_type="job_invite",
            title="Job invitation",
            body=f'An employer invited your community to "{job.title}".',
            link_href="/community-admin/jobs",
        )
    except Exception:
        logger.exception(
            "Failed to notify community of invite job_id=%s community_id=%s",
            job_id,
            community_id,
        )

    return jsonify({
        "message": "Invitation sent.",
        "community_application": application.to_dict(include_community=True, include_job=True),
    }), 201


def get_applications_for_job(job_id, poster_user_id):
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.posted_by_id != poster_user_id:
        return jsonify({"error": "Forbidden."}), 403

    applications = CommunityApplication.query.filter_by(job_id=job_id).all()
    result = []
    for app in applications:
        app_data = app.to_dict(include_community=True)
        community = Community.query.get(app.community_id)
        if community:
            members = CommunityMember.query.filter_by(
                community_id=community.id, status="approved"
            ).all()
            app_data["community"]["members"] = [
                m.to_dict(include_user=True, include_user_skills=True) for m in members
            ]
        result.append(app_data)
    return jsonify({"community_applications": result}), 200


def get_my_applications(user_id):
    admin_ids = get_admin_community_ids(user_id)
    if not admin_ids:
        return jsonify({"community_applications": []}), 200
    applications = CommunityApplication.query.filter(
        CommunityApplication.community_id.in_(admin_ids)
    ).all()
    return jsonify({"community_applications": [a.to_dict(include_job=True) for a in applications]}), 200


def _create_contract_from_application(application, job, commission_percent):
    """Shared Contract + Conversation creation used by employer approve and invite accept."""
    application.status = "approved"
    job.status = "assigned"

    others = CommunityApplication.query.filter(
        CommunityApplication.job_id == job.id,
        CommunityApplication.id != application.id,
    ).all()
    for other in others:
        other.status = "rejected"

    contract = Contract(
        job_id=job.id,
        community_id=application.community_id,
        total_amount=application.proposed_cost,
        commission_percent=commission_percent,
        status="pending_assignment",
    )
    db.session.add(contract)
    db.session.flush()

    conversation = Conversation(contract_id=contract.id)
    db.session.add(conversation)
    return contract, conversation, others


def approve_community(application_id, user_id, data=None):
    """Approve an application and create a Contract.

    - source=applied: job poster only
    - source=invited: community admin only (employer cannot force-accept)
    """
    data = data or {}
    application = CommunityApplication.query.get(application_id)
    if not application:
        return jsonify({"error": "Community application not found."}), 404
    if application.status != "applied":
        return jsonify({"error": "Application is no longer pending."}), 400

    job = Job.query.get(application.job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.status != "open":
        return jsonify({"error": "Job is no longer open."}), 400

    source = application.source or "applied"
    if source == "invited":
        if not is_community_admin(user_id, application.community_id):
            return jsonify({
                "error": "Only the community admin can accept an employer invitation."
            }), 403
    else:
        if job.posted_by_id != int(user_id):
            return jsonify({"error": "Forbidden."}), 403

    commission_percent = _validate_commission_percent(data.get("commission_percent"))
    if commission_percent is None:
        return jsonify({"error": "commission_percent must be between 2 and 5."}), 400

    contract, conversation, others = _create_contract_from_application(
        application, job, commission_percent
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to approve community."}), 500

    try:
        job_title = job.title
        notify_job_application_approved(application.community_id, job_title, contract.id)
        for other in others:
            notify_job_application_rejected(other.community_id, job_title)
        if source == "invited" and job.posted_by_id:
            from app.utils.notification_utils import deliver_notification

            deliver_notification(
                job.posted_by_id,
                notification_type="job_invite_accepted",
                title="Invitation accepted",
                body=f'A community accepted your invitation for "{job_title}".',
                link_href=f"/contracts/{contract.id}",
            )
    except Exception:
        logger.exception(
            "Failed to send job application notifications application_id=%s", application_id
        )

    message = (
        "Invitation accepted. Contract created."
        if source == "invited"
        else "Community approved. Contract created."
    )
    return jsonify({
        "message": message,
        "community_application": application.to_dict(),
        "contract": contract.to_dict(include_job=True),
        "conversation": conversation.to_dict(),
    }), 200


def reject_community(application_id, user_id):
    """Reject an application.

    - source=applied: job poster only
    - source=invited: community admin only
    """
    application = CommunityApplication.query.get(application_id)
    if not application:
        return jsonify({"error": "Community application not found."}), 404
    if application.status != "applied":
        return jsonify({"error": "Application is no longer pending."}), 400

    job = Job.query.get(application.job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404

    source = application.source or "applied"
    if source == "invited":
        if not is_community_admin(user_id, application.community_id):
            return jsonify({
                "error": "Only the community admin can decline an employer invitation."
            }), 403
    else:
        if job.posted_by_id != int(user_id):
            return jsonify({"error": "Forbidden."}), 403

    application.status = "rejected"
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to reject application."}), 500

    try:
        if source == "invited" and job.posted_by_id:
            from app.utils.notification_utils import deliver_notification

            deliver_notification(
                job.posted_by_id,
                notification_type="job_invite_declined",
                title="Invitation declined",
                body=f'A community declined your invitation for "{job.title}".',
                link_href=f"/jobs/{job.id}/applicants",
            )
        elif source != "invited":
            notify_job_application_rejected(application.community_id, job.title)
    except Exception:
        logger.exception(
            "Failed to send job rejection notification application_id=%s", application_id
        )

    message = "Invitation declined." if source == "invited" else "Application rejected."
    return jsonify({"message": message, "community_application": application.to_dict()}), 200
