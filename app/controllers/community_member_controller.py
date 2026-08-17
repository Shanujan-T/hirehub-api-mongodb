import logging

from flask import jsonify

from app.extensions import db
from app.middleware import is_community_admin
from app.models.community_member_model import CommunityMember
from app.models.community_model import Community
from app.models.user_model import User
from app.utils import utc_now
from app.utils.notification_utils import notify_community_join_request, notify_membership_decision

logger = logging.getLogger(__name__)


def request_join(community_id, user_id):
    user_id = int(user_id)
    community = Community.query.get(community_id)
    if not community or community.status != "approved":
        return jsonify({"error": "Community is not available for join requests."}), 400

    existing = CommunityMember.query.filter_by(
        community_id=community_id, user_id=user_id
    ).first()
    if existing:
        return jsonify({"error": "Already requested or member."}), 409

    from app.models.user_skill_model import UserSkill
    skill_count = UserSkill.query.filter_by(user_id=user_id).count()
    if skill_count == 0:
        return jsonify({"error": "Add at least one skill to your profile before joining a community."}), 400

    membership = CommunityMember(
        community_id=community_id,
        user_id=user_id,
        role="member",
        status="pending",
    )
    db.session.add(membership)
    try:
        db.session.commit()
        logger.info(
            "Join request created membership_id=%s community_id=%s user_id=%s status=%s role=%s",
            membership.id,
            membership.community_id,
            membership.user_id,
            membership.status,
            membership.role,
        )
        admin_row = CommunityMember.query.filter_by(
            community_id=community_id, role="admin"
        ).first()
        logger.info(
            "Pre-notify admin lookup community_id=%s first_admin_row=%s",
            community_id,
            {
                "membership_id": admin_row.id,
                "user_id": admin_row.user_id,
                "role": admin_row.role,
                "status": admin_row.status,
            }
            if admin_row
            else None,
        )
        if not admin_row:
            logger.warning("NO ADMIN FOUND for community_id=%s", community_id)
        try:
            requesting_user = User.query.get(user_id)
            if requesting_user and community:
                logger.info(
                    "Calling notify_community_join_request community_id=%s membership_id=%s requester_user_id=%s admin_target=%s",
                    community_id,
                    membership.id,
                    user_id,
                    admin_row.user_id if admin_row else None,
                )
                notify_community_join_request(
                    community_id=community_id,
                    membership_id=membership.id,
                    requester_name=requesting_user.full_name,
                    community_name=community.name,
                    requester_user_id=user_id,
                )
                logger.info(
                    "notify_community_join_request completed community_id=%s membership_id=%s",
                    community_id,
                    membership.id,
                )
            else:
                logger.warning(
                    "Skipped join notification — missing user or community community_id=%s user_id=%s",
                    community_id,
                    user_id,
                )
        except Exception:
            logger.exception(
                "Failed to notify admins of join request community_id=%s membership_id=%s",
                community_id,
                membership.id,
            )
        return jsonify({"message": "Join request submitted.", "community_member": membership.to_dict()}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to submit join request."}), 500


def get_community_members(community_id, status=None):
    query = CommunityMember.query.filter_by(community_id=community_id)
    if status:
        query = query.filter_by(status=status)
    members = query.all()
    return jsonify(
        {
            "community_members": [
                m.to_dict(include_user=True, include_user_skills=True) for m in members
            ]
        }
    ), 200


def get_my_memberships(user_id):
    memberships = CommunityMember.query.filter_by(user_id=user_id).all()
    result = []
    for membership in memberships:
        row = membership.to_dict()
        if membership.community:
            row["community"] = membership.community.to_dict(include_category=True)
        result.append(row)
    return jsonify({"community_members": result}), 200


def approve_member(membership_id, admin_user_id, action):
    membership = CommunityMember.query.get(membership_id)
    if not membership:
        return jsonify({"error": "Community member not found."}), 404
    if not is_community_admin(admin_user_id, membership.community_id):
        return jsonify({"error": "Forbidden."}), 403
    if action == "approve":
        membership.status = "approved"
        membership.joined_at = utc_now()
    elif action == "reject":
        membership.status = "rejected"
    else:
        return jsonify({"error": "Invalid action."}), 400
    try:
        db.session.commit()
        try:
            community_name = membership.community.name if membership.community else "the community"
            notify_membership_decision(
                membership.user_id,
                community_name,
                approved=(action == "approve"),
            )
        except Exception:
            logger.exception(
                "Failed to notify member of join decision membership_id=%s",
                membership_id,
            )
        return jsonify({"message": f"Member {action}d.", "community_member": membership.to_dict(include_user=True)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update membership."}), 500


def delete_community_member(membership_id, user_id):
    membership = CommunityMember.query.get(membership_id)
    if not membership:
        return jsonify({"error": "Community member not found."}), 404

    is_admin = is_community_admin(user_id, membership.community_id)
    is_self = membership.user_id == user_id

    if is_admin:
        if is_self:
            return jsonify({"error": "Community admins cannot remove themselves."}), 403
    elif not is_self:
        return jsonify({"error": "Forbidden."}), 403
    try:
        db.session.delete(membership)
        db.session.commit()
        return jsonify({"message": "Membership removed."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to remove membership."}), 500
