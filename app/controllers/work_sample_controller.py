"""Work sample upload + AI skill verification."""

from __future__ import annotations

from flask import jsonify, request

from app.extensions import db
from app.models.user_skill_model import UserSkill
from app.models.work_sample_model import WorkSample
from app.utils.ai_client import (
    ask_ai,
    ask_ai_with_image,
    check_ai_cooldown,
    cooldown_response,
    mark_ai_call,
)
from app.utils.cloudinary_client import upload_image, validate_image_file
from app.controllers.ai_features_controller import _parse_json_object


def _owned_user_skill(user_skill_id: int, user_id: int):
    us = UserSkill.query.get(user_skill_id)
    if not us:
        return None, (jsonify({"error": "User skill not found."}), 404)
    if us.user_id != int(user_id):
        return None, (jsonify({"error": "Forbidden."}), 403)
    return us, None


def create_work_sample(user_skill_id: int, user_id: int):
    """Accept JSON {sample_type, content} or multipart image upload."""
    us, error = _owned_user_skill(user_skill_id, user_id)
    if error:
        return error

    sample_type = None
    content = None

    if request.content_type and "multipart/form-data" in request.content_type:
        sample_type = (request.form.get("sample_type") or "image").strip().lower()
        if sample_type != "image":
            return jsonify({"errors": ["multipart uploads must use sample_type=image."]}), 400
        file_storage = request.files.get("file") or request.files.get("image")
        validation_error = validate_image_file(file_storage)
        if validation_error:
            return jsonify({"errors": [validation_error]}), 400
        try:
            content = upload_image(file_storage, folder="hirehub/work-samples")
        except ValueError as exc:
            return jsonify({"errors": [str(exc)]}), 400
        except Exception:
            return jsonify({"error": "Image upload failed."}), 500
    else:
        data = request.get_json(silent=True) or {}
        sample_type = str(data.get("sample_type") or "text").strip().lower()
        content = (data.get("content") or "").strip()
        if sample_type not in ("text", "image"):
            return jsonify({"errors": ["sample_type must be text or image."]}), 400
        if not content:
            return jsonify({"errors": ["content is required."]}), 400
        if sample_type == "image" and not content.startswith(("http://", "https://")):
            return jsonify({"errors": ["image content must be a URL."]}), 400

    sample = WorkSample(
        user_skill_id=us.id,
        sample_type=sample_type,
        content=content,
        verification_status="unreviewed",
    )
    db.session.add(sample)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to save work sample."}), 500

    # Auto-verify when possible; never block the upload on AI failure.
    vision_available = None
    message = None
    allowed, _retry = check_ai_cooldown(user_id, "skill_verify")
    if allowed:
        verify_result = _run_verify(sample, us, user_id, force=True)
        vision_available = verify_result.get("vision_available")
        message = verify_result.get("message")
    else:
        message = "AI cooling down — sample saved as unreviewed; verify again shortly."

    return jsonify(
        {
            "work_sample": sample.to_dict(),
            "user_skill": us.to_dict(include_samples=True),
            "vision_available": vision_available,
            "message": message,
        }
    ), 201


def list_work_samples(user_skill_id: int, user_id: int):
    us, error = _owned_user_skill(user_skill_id, user_id)
    if error:
        return error
    return jsonify({"user_skill": us.to_dict(include_samples=True)}), 200


def verify_work_sample(sample_id: int, user_id: int):
    sample = WorkSample.query.get(sample_id)
    if not sample:
        return jsonify({"error": "Work sample not found."}), 404
    us, error = _owned_user_skill(sample.user_skill_id, user_id)
    if error:
        return error

    allowed, retry_after = check_ai_cooldown(user_id, "skill_verify")
    if not allowed:
        return cooldown_response(retry_after)

    result = _run_verify(sample, us, user_id, force=True)
    return jsonify(
        {
            "work_sample": sample.to_dict(),
            "user_skill": us.to_dict(include_samples=True),
            **result,
        }
    ), 200


def _run_verify(sample: WorkSample, us: UserSkill, user_id: int, *, force: bool) -> dict:
    skill_name = us.skill.name if us.skill else "this skill"
    vision_available = True

    if sample.sample_type == "text":
        if force:
            mark_ai_call(user_id, "skill_verify")
        raw = ask_ai(
            system_prompt=(
                "You assess whether a work sample plausibly demonstrates a claimed skill. "
                'Reply ONLY with JSON: {"assessment":"one short sentence","status":"plausible"|"unclear"}'
            ),
            user_prompt=(
                f"Claimed skill: {skill_name}\n"
                f"Work sample (text):\n{sample.content[:4000]}\n"
                "Is this a plausible demonstration of the skill?"
            ),
            max_tokens=180,
        )
        parsed = _parse_json_object(raw)
        if not parsed:
            sample.verification_status = "unreviewed"
            sample.ai_assessment = None
            db.session.commit()
            return {
                "available": False,
                "message": "AI verification unavailable — sample left unreviewed.",
                "vision_available": None,
            }
        status = str(parsed.get("status") or "").strip().lower()
        if status not in ("plausible", "unclear"):
            status = "unclear"
        sample.verification_status = status
        sample.ai_assessment = str(parsed.get("assessment") or "").strip() or None
        db.session.commit()
        return {"available": True, "vision_available": None, "message": None}

    # Image — best-effort vision
    if force:
        mark_ai_call(user_id, "skill_verify")
    raw = ask_ai_with_image(
        system_prompt=(
            "You assess whether an image work sample plausibly demonstrates a claimed skill. "
            'Reply ONLY with JSON: {"assessment":"one short sentence","status":"plausible"|"unclear"}'
        ),
        user_prompt=(
            f"Claimed skill: {skill_name}\n"
            "Does this image look like a plausible demonstration of the skill?"
        ),
        image_url=sample.content,
        max_tokens=180,
    )
    parsed = _parse_json_object(raw)
    if not parsed:
        sample.verification_status = "unreviewed"
        sample.ai_assessment = None
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return {
            "available": False,
            "vision_available": False,
            "message": "Image review temporarily unavailable — try a text description instead.",
        }

    status = str(parsed.get("status") or "").strip().lower()
    if status not in ("plausible", "unclear"):
        status = "unclear"
    sample.verification_status = status
    sample.ai_assessment = str(parsed.get("assessment") or "").strip() or None
    db.session.commit()
    return {
        "available": True,
        "vision_available": vision_available,
        "message": None,
    }
