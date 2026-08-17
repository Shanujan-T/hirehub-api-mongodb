from flask import jsonify

from app.extensions import db
from app.models.user_skill_model import UserSkill


def _validate_user_skill_payload(data):
    errors = []
    if not data.get("user_id"):
        errors.append("user_id is required.")
    if not data.get("skill_id"):
        errors.append("skill_id is required.")
    level = data.get("level", "intermediate")
    if level not in ("beginner", "intermediate", "advanced", "expert"):
        errors.append("level must be beginner, intermediate, advanced, or expert.")
    return errors


def create_user_skill(data):
    errors = _validate_user_skill_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400
    existing = UserSkill.query.filter_by(
        user_id=data["user_id"], skill_id=data["skill_id"]
    ).first()
    if existing:
        return jsonify({"error": "User already has this skill."}), 409
    us = UserSkill(
        user_id=data["user_id"],
        skill_id=data["skill_id"],
        level=data.get("level", "intermediate"),
    )
    db.session.add(us)
    try:
        db.session.commit()
        return jsonify({"message": "User skill created.", "user_skill": us.to_dict()}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to create user skill."}), 500


def get_user_skills(user_id=None):
    query = UserSkill.query
    if user_id:
        query = query.filter_by(user_id=user_id)
    items = query.all()
    return jsonify({"user_skills": [u.to_dict() for u in items]}), 200


def get_user_skill(user_skill_id):
    us = UserSkill.query.get(user_skill_id)
    if not us:
        return jsonify({"error": "User skill not found."}), 404
    return jsonify({"user_skill": us.to_dict()}), 200


def update_user_skill(user_skill_id, data):
    us = UserSkill.query.get(user_skill_id)
    if not us:
        return jsonify({"error": "User skill not found."}), 404
    if "level" in data:
        us.level = data["level"]
    try:
        db.session.commit()
        return jsonify({"message": "User skill updated.", "user_skill": us.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update user skill."}), 500


def delete_user_skill(user_skill_id):
    us = UserSkill.query.get(user_skill_id)
    if not us:
        return jsonify({"error": "User skill not found."}), 404
    try:
        db.session.delete(us)
        db.session.commit()
        return jsonify({"message": "User skill deleted."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete user skill."}), 500
