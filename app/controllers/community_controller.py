from flask import jsonify

from app.extensions import db
from app.middleware import get_admin_community_ids, is_community_admin
from app.models.category_model import Category
from app.models.community_member_model import CommunityMember
from app.models.community_model import Community
from app.models.user_model import User
from app.utils import utc_now
from app.utils.cloudinary_client import upload_image
from app.utils.notification_utils import notify_community_verification

VALID_EXPERIENCE_LEVELS = {"less_than_1_year", "1_to_3_years", "3_plus_years"}


def _validate_community_payload(data, *, require_review_fields=False):
    errors = []
    name = str(data.get("name", "")).strip()
    if not name:
        errors.append("name is required.")

    if require_review_fields:
        category_id = data.get("category_id")
        if not category_id:
            errors.append("category_id is required.")
        else:
            category = Category.query.get(category_id)
            if not category or category.status != "approved":
                errors.append("category_id is invalid.")
        experience_level = data.get("experience_level")
        if not experience_level:
            errors.append("experience_level is required.")
        elif experience_level not in VALID_EXPERIENCE_LEVELS:
            errors.append("experience_level is invalid.")
        if not data.get("terms_accepted"):
            errors.append("terms_accepted must be true.")

    return errors, name


def _community_admin_user(community_id):
    membership = CommunityMember.query.filter_by(
        community_id=community_id, role="admin", status="approved"
    ).first()
    if not membership or not membership.user:
        membership = CommunityMember.query.filter_by(
            community_id=community_id, role="admin"
        ).order_by(CommunityMember.id.asc()).first()
    return membership.user if membership else None


def _community_dict(community, **kwargs):
    return community.to_dict(**kwargs)


def create_community(data, user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    if user.identity_status != "verified":
        return jsonify({"error": "Account verification required before creating a community."}), 403

    errors, name = _validate_community_payload(data, require_review_fields=True)
    if errors:
        return jsonify({"errors": errors}), 400
    if Community.query.filter_by(name=name).first():
        return jsonify({"errors": ["Community name already exists."]}), 400

    description = data.get("description")
    if isinstance(description, str):
        description = description.strip() or None
    location = data.get("location")
    if isinstance(location, str):
        location = location.strip() or None

    specialization = data.get("specialization")
    if isinstance(specialization, str):
        specialization = specialization.strip() or None

    admin_bio = data.get("admin_bio")
    if isinstance(admin_bio, str):
        admin_bio = admin_bio.strip() or None

    contact_phone = data.get("contact_phone")
    if isinstance(contact_phone, str):
        contact_phone = contact_phone.strip() or None

    portfolio_links = data.get("portfolio_links") or []
    if not isinstance(portfolio_links, list):
        return jsonify({"errors": ["portfolio_links must be an array."]}), 400
    portfolio_links = [str(link).strip() for link in portfolio_links if str(link).strip()]

    community = Community(
        name=name,
        description=description,
        location=location,
        category_id=int(data["category_id"]),
        experience_level=data["experience_level"],
        specialization=specialization,
        portfolio_links=portfolio_links or None,
        admin_bio=admin_bio,
        contact_phone=contact_phone,
        status="pending",
    )
    db.session.add(community)
    db.session.flush()

    membership = CommunityMember(
        community_id=community.id,
        user_id=user_id,
        role="admin",
        status="approved",
        joined_at=utc_now(),
    )
    db.session.add(membership)
    try:
        db.session.commit()
        return jsonify({
            "message": "Community submitted for review.",
            "community": _community_dict(community, include_member_count=True, include_category=True),
        }), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to create community."}), 500


def get_communities(current_user_role=None, status_filter=None):
    query = Community.query
    if current_user_role == "admin":
        if status_filter:
            query = query.filter_by(status=status_filter)
    else:
        query = query.filter_by(status="approved")

    communities = query.order_by(Community.created_at.desc()).all()
    return jsonify({
        "communities": [
            _community_dict(c, include_member_count=True, include_category=True) for c in communities
        ]
    }), 200


def get_community(community_id, current_user_id=None, current_user_role=None):
    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found."}), 404

    is_admin = current_user_role == "admin"
    is_member = False
    if current_user_id:
        is_member = (
            CommunityMember.query.filter_by(
                community_id=community_id,
                user_id=current_user_id,
                status="approved",
            ).first()
            is not None
        )

    if community.status != "approved" and not is_admin and not is_member:
        return jsonify({"error": "Community not found."}), 404

    data = _community_dict(community, include_member_count=True, include_category=True)
    members = CommunityMember.query.filter_by(
        community_id=community_id, status="approved"
    ).all()
    data["members"] = [
        m.to_dict(include_user=True, include_user_skills=True) for m in members
    ]

    if is_admin:
        admin_user = _community_admin_user(community_id)
        if admin_user:
            data["admin_user"] = admin_user.to_dict(viewer_role="admin", include_stats=True)

    return jsonify({"community": data}), 200


def update_community(community_id, data, user_id):
    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found."}), 404
    if not is_community_admin(user_id, community_id):
        return jsonify({"error": "Community admin access required."}), 403
    if "category_id" in data:
        return jsonify({"error": "category_id cannot be changed."}), 400

    errors = []
    name = community.name
    if "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            errors.append("name is required.")

    location = community.location
    if "location" in data:
        location = str(data.get("location") or "").strip()
        if not location:
            errors.append("location is required.")

    description = community.description
    if "description" in data:
        raw = data.get("description")
        description = str(raw).strip() if isinstance(raw, str) else None
        if description == "":
            description = None

    if errors:
        return jsonify({"errors": errors}), 400

    if name != community.name:
        conflict = Community.query.filter(
            Community.name == name, Community.id != community_id
        ).first()
        if conflict:
            return jsonify({"errors": ["Community name already exists."]}), 400

    community.name = name
    community.location = location
    if "description" in data:
        community.description = description

    try:
        db.session.commit()
        return jsonify({
            "message": "Community updated.",
            "community": _community_dict(community, include_member_count=True, include_category=True),
        }), 200
    except Exception:
        db.session.rollback()
        conflict = Community.query.filter(
            Community.name == name, Community.id != community_id
        ).first()
        if conflict:
            return jsonify({"errors": ["Community name already exists."]}), 400
        return jsonify({"error": "Failed to update community."}), 500


def _apply_verification_status(community, verification_status, reason=None):
    if verification_status == "verified":
        community.status = "approved"
        community.rejection_reason = None
    elif verification_status == "rejected":
        community.status = "rejected"
        community.rejection_reason = reason
    else:
        return jsonify({"errors": ["verification_status must be 'verified' or 'rejected'."]}), 400
    return None


def verify_community(community_id, data):
    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found."}), 404

    verification_status = data.get("verification_status")
    if verification_status is None and "approve" in data:
        verification_status = "verified" if bool(data.get("approve")) else "rejected"
    if verification_status not in ("verified", "rejected"):
        return jsonify({"errors": ["verification_status must be 'verified' or 'rejected'."]}), 400

    reason = data.get("reason")
    if isinstance(reason, str):
        reason = reason.strip() or None

    error = _apply_verification_status(community, verification_status, reason)
    if error:
        return error

    try:
        db.session.commit()
        notify_community_verification(
            community_id,
            community.name,
            verified=(verification_status == "verified"),
            reason=reason,
        )
        payload = _community_dict(community, include_member_count=True, include_category=True)
        admin_user = _community_admin_user(community_id)
        if admin_user:
            payload["admin_user"] = admin_user.to_dict(viewer_role="admin", include_stats=True)
        return jsonify({"message": "Community verification updated.", "community": payload}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to verify community."}), 500


def review_community(community_id, data):
    return verify_community(community_id, data)


def delete_community(community_id, user_id):
    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found."}), 404
    admin_ids = get_admin_community_ids(user_id)
    if community_id not in admin_ids:
        return jsonify({"error": "Forbidden."}), 403
    try:
        db.session.delete(community)
        db.session.commit()
        return jsonify({"message": "Community deleted."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete community."}), 500


def upload_community_image(community_id, user_id, file_storage):
    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found."}), 404

    if not is_community_admin(user_id, community_id):
        return jsonify({"error": "Community admin access required."}), 403

    try:
        image_url = upload_image(file_storage, "hirehub/communities")
    except ValueError as exc:
        return jsonify({"errors": [str(exc)]}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        return jsonify({"error": "Failed to upload community image."}), 500

    community.image_url = image_url
    try:
        db.session.commit()
        return jsonify({
            "message": "Community image updated.",
            "community": _community_dict(community, include_member_count=True, include_category=True),
        }), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to save community image."}), 500
