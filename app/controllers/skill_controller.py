from flask import jsonify

from app.extensions import db
from app.models.skill_model import Skill


def _validate_skill_payload(data):
    errors = []
    if not data.get("name"):
        errors.append("name is required.")
    return errors


def create_skill(data):
    errors = _validate_skill_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400
    if Skill.query.filter_by(name=data["name"]).first():
        return jsonify({"error": "Skill already exists."}), 409
    skill = Skill(name=data["name"], category=data.get("category"))
    db.session.add(skill)
    try:
        db.session.commit()
        return jsonify({"message": "Skill created.", "skill": skill.to_dict()}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to create skill."}), 500


def get_skills():
    skills = Skill.query.all()
    return jsonify({"skills": [s.to_dict() for s in skills]}), 200


def get_skill(skill_id):
    skill = Skill.query.get(skill_id)
    if not skill:
        return jsonify({"error": "Skill not found."}), 404
    return jsonify({"skill": skill.to_dict()}), 200


def update_skill(skill_id, data):
    skill = Skill.query.get(skill_id)
    if not skill:
        return jsonify({"error": "Skill not found."}), 404
    if "name" in data:
        skill.name = data["name"]
    if "category" in data:
        skill.category = data["category"]
    try:
        db.session.commit()
        return jsonify({"message": "Skill updated.", "skill": skill.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update skill."}), 500


def delete_skill(skill_id):
    skill = Skill.query.get(skill_id)
    if not skill:
        return jsonify({"error": "Skill not found."}), 404
    try:
        db.session.delete(skill)
        db.session.commit()
        return jsonify({"message": "Skill deleted."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete skill."}), 500
