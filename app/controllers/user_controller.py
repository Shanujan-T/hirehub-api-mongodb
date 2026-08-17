import logging
import os
import re

from flask import jsonify

from app.extensions import db
from app.models.user_model import User
from app.models.verification_otp_model import VerificationOtp
from app.utils import utc_now

from app.utils.cloudinary_client import delete_image, upload_image
from app.utils.otp_delivery import send_identity_sms_otp
from app.utils.otp_utils import generate_otp_code, hash_otp_code, otp_expires_at, verify_otp_code
from app.utils.sms_client import is_twilio_configured, send_verification_code, check_verification_code
from app.utils.email_client import send_otp_email

logger = logging.getLogger(__name__)

_DEPRECATED_NIC_MESSAGE = (
    "NIC document verification has been removed. Confirm your phone or email with a one-time code instead."
)

_PHONE_RE = re.compile(r"^\+?[0-9]{8,15}$")

_ADDRESS_FIELDS = (
    "address_line1",
    "address_line2",
    "address_city",
    "address_region",
    "address_postal_code",
)


def _optional_str(value, *, max_len: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed[:max_len]


def _validate_user_payload(data, user_id=None):
    errors = []
    if not user_id:
        if not data.get("email"):
            errors.append("email is required.")
        if not data.get("full_name"):
            errors.append("full_name is required.")
    elif "full_name" in data and not str(data.get("full_name", "")).strip():
        errors.append("full_name is required.")
    return errors


def _user_dict(user, viewer_id=None, viewer_role=None, **kwargs):
    return user.to_dict(viewer_id=viewer_id, viewer_role=viewer_role, **kwargs)


def get_users():
    users = User.query.all()
    return jsonify({
        "users": [_user_dict(u, viewer_role="admin", include_stats=True) for u in users]
    }), 200


def get_user(user_id, current_user_id=None, current_user_role=None):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    is_admin = current_user_role == "admin"
    is_self = current_user_id == user_id
    if not is_admin and not is_self:
        return jsonify({"error": "Forbidden."}), 403

    include_skills = is_admin and user.role == "employer"
    data = _user_dict(
        user,
        viewer_id=current_user_id,
        viewer_role=current_user_role,
        include_stats=True,
        include_skills=include_skills,
    )

    if is_admin:
        from app.models.community_member_model import CommunityMember

        memberships = CommunityMember.query.filter_by(user_id=user_id).all()
        data["community_memberships"] = []
        for membership in memberships:
            row = membership.to_dict()
            if membership.community:
                row["community"] = {
                    "id": membership.community.id,
                    "name": membership.community.name,
                }
            data["community_memberships"].append(row)

    return jsonify({"user": data}), 200


def update_user(user_id, data, current_user_id, current_user_role=None):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    is_admin = current_user_role == "admin"
    is_self = user.id == current_user_id

    if "is_active" in data and not is_admin:
        return jsonify({"error": "Forbidden."}), 403

    if is_admin and not is_self:
        if set(data.keys()) - {"is_active"}:
            return jsonify({"error": "Admins may only change account status for other users."}), 403
    elif not is_self:
        return jsonify({"error": "Forbidden."}), 403

    errors = _validate_user_payload(data, user_id if is_self else user_id)
    if errors and is_self:
        return jsonify({"errors": errors}), 400

    if "is_active" in data and is_admin:
        user.is_active = bool(data["is_active"])

    if is_self:
        if "full_name" in data:
            user.full_name = str(data["full_name"]).strip()
        if "bio" in data:
            user.bio = data["bio"]
        if "location" in data:
            location = data["location"]
            user.location = location.strip() if isinstance(location, str) and location.strip() else None
        if "avatar_url" in data:
            user.avatar_url = data["avatar_url"]
        limits = {
            "address_line1": 255,
            "address_line2": 255,
            "address_city": 128,
            "address_region": 128,
            "address_postal_code": 32,
        }
        for field in _ADDRESS_FIELDS:
            if field in data:
                setattr(user, field, _optional_str(data.get(field), max_len=limits[field]))

    try:
        db.session.commit()
        return jsonify({
            "message": "User updated.",
            "user": _user_dict(user, viewer_id=current_user_id, viewer_role=current_user_role, include_stats=True),
        }), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update user."}), 500


def upload_avatar(user_id, current_user_id, current_user_role, file_storage):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    is_admin = current_user_role == "admin"
    is_self = user.id == current_user_id
    if not is_admin and not is_self:
        return jsonify({"error": "Forbidden."}), 403

    try:
        avatar_url = upload_image(file_storage, "hirehub/users")
    except ValueError as exc:
        return jsonify({"errors": [str(exc)]}), 400
    except RuntimeError as exc:
        logger.exception("Avatar storage unavailable for user_id=%s", user_id)
        return jsonify({"error": str(exc)}), 503
    except Exception:
        logger.exception("Unexpected avatar upload failure for user_id=%s", user_id)
        db.session.rollback()
        return jsonify({"error": "Failed to upload avatar."}), 500

    user.avatar_url = avatar_url
    try:
        db.session.commit()
        return jsonify({
            "message": "Avatar updated.",
            "user": _user_dict(user, viewer_id=current_user_id, viewer_role=current_user_role, include_stats=True),
        }), 200
    except Exception:
        logger.exception("Failed to persist avatar URL for user_id=%s", user_id)
        db.session.rollback()
        return jsonify({"error": "Failed to save avatar."}), 500


def delete_avatar(user_id, current_user_id, current_user_role):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    is_admin = current_user_role == "admin"
    is_self = user.id == current_user_id
    if not is_admin and not is_self:
        return jsonify({"error": "Forbidden."}), 403

    try:
        delete_image(user.avatar_url)
        user.avatar_url = None
        db.session.commit()
        return jsonify({
            "message": "Avatar removed.",
            "user": _user_dict(user, viewer_id=current_user_id, viewer_role=current_user_role, include_stats=True),
        }), 200
    except RuntimeError as exc:
        logger.exception("Avatar storage deletion failed for user_id=%s", user_id)
        db.session.rollback()
        return jsonify({"error": str(exc)}), 503
    except Exception:
        logger.exception("Unexpected avatar deletion failure for user_id=%s", user_id)
        db.session.rollback()
        return jsonify({"error": "Failed to remove profile picture."}), 500


def _normalize_phone(raw: str) -> str | None:
    cleaned = re.sub(r"[\s\-()]", "", str(raw or "").strip())
    if not cleaned:
        return None
    if cleaned.startswith("00"):
        cleaned = f"+{cleaned[2:]}"
    if not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"
    if not _PHONE_RE.match(cleaned):
        return None
    return cleaned


def _store_otp(user_id: int, purpose: str, code: str) -> None:
    VerificationOtp.query.filter_by(user_id=user_id, purpose=purpose).delete()
    db.session.add(
        VerificationOtp(
            user_id=user_id,
            purpose=purpose,
            code_hash=hash_otp_code(code),
            expires_at=otp_expires_at(),
        )
    )


def _consume_otp(user_id: int, purpose: str, code: str) -> bool:
    row = (
        VerificationOtp.query.filter_by(user_id=user_id, purpose=purpose)
        .order_by(VerificationOtp.id.desc())
        .first()
    )
    if not row or row.expires_at < utc_now():
        return False
    if not verify_otp_code(code, row.code_hash):
        return False
    VerificationOtp.query.filter_by(user_id=user_id, purpose=purpose).delete()
    return True


def _identity_user_response(user, user_id):
    return jsonify({
        "message": "Account verification updated.",
        "user": _user_dict(user, viewer_id=user_id, viewer_role=user.role, include_stats=True),
    }), 200


def upload_nic_document(user_id, file_storage):
    return jsonify({"error": _DEPRECATED_NIC_MESSAGE}), 410


def submit_identity_verification(user_id, data):
    return jsonify({"error": _DEPRECATED_NIC_MESSAGE}), 410


def send_identity_phone_otp(user_id, data):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    if user.identity_status == "verified":
        return jsonify({"error": "Account is already verified."}), 400

    phone = _normalize_phone(data.get("phone_number", ""))
    if not phone:
        return jsonify({"errors": ["phone_number is invalid."]}), 400

    if is_twilio_configured():
        try:
            send_verification_code(phone)
            user.phone_number = phone
            db.session.commit()
            return jsonify({"message": "Verification code sent via SMS."}), 200
        except Exception as e:
            logger.exception("Twilio Verify send failed: %s", e)
            return jsonify({"error": "Couldn't send code, please check the number and try again."}), 400

    code = generate_otp_code()
    _store_otp(user_id, "identity_phone", code)
    user.phone_number = phone
    send_identity_sms_otp(phone, code)

    try:
        db.session.commit()
        return jsonify({"message": "Verification code sent via SMS."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to send phone verification code."}), 500


def confirm_identity_phone_otp(user_id, data):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    if user.identity_status == "verified":
        return jsonify({"error": "Account is already verified."}), 400

    code = str(data.get("code", "")).strip()
    if not code:
        return jsonify({"errors": ["code is required."]}), 400

    if is_twilio_configured():
        if not user.phone_number:
            return jsonify({"error": "No phone number associated with this request. Please send a code first."}), 400
        try:
            approved = check_verification_code(user.phone_number, code)
            if not approved:
                return jsonify({"error": "Invalid or expired verification code."}), 400
        except Exception as e:
            logger.exception("Twilio Verify check failed: %s", e)
            return jsonify({"error": "Failed to confirm phone verification, please try again."}), 400
    else:
        if not _consume_otp(user_id, "identity_phone", code):
            return jsonify({"error": "Invalid or expired verification code."}), 400

    user.phone_verified_at = utc_now()
    user.sync_identity_verification_status()

    try:
        db.session.commit()
        return _identity_user_response(user, user_id)
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to confirm phone verification."}), 500


def send_identity_email_otp(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    if user.identity_status == "verified":
        return jsonify({"error": "Account is already verified."}), 400

    code = generate_otp_code()
    _store_otp(user_id, "identity_email", code)

    if not os.getenv("BREVO_API_KEY"):
        db.session.rollback()
        logger.error("Email OTP delivery is unavailable because Brevo is not configured.")
        return jsonify({"error": "Email verification delivery is not configured."}), 503

    try:
        send_otp_email(user.email, code)
    except Exception as e:
        logger.exception("Failed to send identity email OTP: %s", e)
        db.session.rollback()
        return jsonify({"error": "Failed to send email verification code."}), 502

    try:
        db.session.commit()
        return jsonify({"message": "Verification code sent to your email."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to send email verification code."}), 500


def confirm_identity_email_otp(user_id, data):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    if user.identity_status == "verified":
        return jsonify({"error": "Account is already verified."}), 400

    code = str(data.get("code", "")).strip()
    if not code:
        return jsonify({"errors": ["code is required."]}), 400
    if not _consume_otp(user_id, "identity_email", code):
        return jsonify({"error": "Invalid or expired verification code."}), 400

    user.email_verified_at = utc_now()
    user.sync_identity_verification_status()

    try:
        db.session.commit()
        return _identity_user_response(user, user_id)
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to confirm email verification."}), 500


def verify_identity(user_id, data):
    return jsonify({"error": _DEPRECATED_NIC_MESSAGE}), 410


def delete_user(user_id, current_user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    if user.id != current_user_id:
        return jsonify({"error": "Forbidden."}), 403
    try:
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": "User deleted."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete user."}), 500
