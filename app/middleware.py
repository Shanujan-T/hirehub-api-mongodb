from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.models.community_member_model import CommunityMember
from app.models.community_model import Community
from app.models.user_model import User


def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user_id = int(get_jwt_identity())
            user = User.query.get(user_id)
            if not user or user.role not in roles:
                return jsonify({"error": "Forbidden."}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def get_current_user():
    verify_jwt_in_request()
    return User.query.get(int(get_jwt_identity()))


def community_admin_required(community_id_param="community_id"):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = User.query.get(get_jwt_identity())
            if not user:
                return jsonify({"error": "Unauthorized."}), 401
            community_id = kwargs.get(community_id_param) or kwargs.get("id")
            if community_id is None:
                from flask import request
                community_id = request.view_args.get(community_id_param) if request.view_args else None
            membership = CommunityMember.query.filter_by(
                community_id=community_id,
                user_id=user.id,
                role="admin",
                status="approved",
            ).first()
            if not membership and user.role != "admin":
                return jsonify({"error": "Community admin access required."}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def member_of_community_required(community_id_param="community_id"):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = User.query.get(get_jwt_identity())
            if not user:
                return jsonify({"error": "Unauthorized."}), 401
            community_id = kwargs.get(community_id_param)
            membership = CommunityMember.query.filter_by(
                community_id=community_id,
                user_id=user.id,
                status="approved",
            ).first()
            if not membership:
                return jsonify({"error": "Community membership required."}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def is_community_admin(user_id, community_id):
    return (
        CommunityMember.query.filter_by(
            community_id=community_id,
            user_id=user_id,
            role="admin",
            status="approved",
        ).first()
        is not None
    )


def get_admin_community_ids(user_id):
    memberships = CommunityMember.query.filter_by(
        user_id=user_id, role="admin", status="approved"
    ).all()
    return [m.community_id for m in memberships]


def can_browse_job_marketplace(user_id):
    """True if user admins at least one verified community with the minimum member count."""
    for community_id in get_admin_community_ids(user_id):
        if community_meets_minimum(community_id):
            return True
    return False


MIN_COMMUNITY_MEMBERS = 3


def community_meets_minimum(community_id):
    """Return True if community is verified and has at least MIN_COMMUNITY_MEMBERS approved members."""
    community = Community.query.get(community_id)
    if not community or community.status != "approved":
        return False
    count = CommunityMember.query.filter_by(
        community_id=community_id, status="approved"
    ).count()
    return count >= MIN_COMMUNITY_MEMBERS
