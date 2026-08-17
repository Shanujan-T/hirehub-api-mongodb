from flask import jsonify

from app.extensions import db
from app.middleware import is_community_admin
from app.models.open_call_model import OpenCall
from app.models.open_call_skill_model import OpenCallSkill


def _validate_open_call_payload(data):
    errors = []
    if not data.get("community_id"):
        errors.append("community_id is required.")
    if not data.get("title"):
        errors.append("title is required.")
    return errors


def _set_open_call_skills(open_call, skill_ids):
    if skill_ids is None:
        return
    OpenCallSkill.query.filter_by(open_call_id=open_call.id).delete()
    for skill_id in skill_ids:
        db.session.add(OpenCallSkill(open_call_id=open_call.id, skill_id=skill_id))


def create_open_call(data, user_id):
    errors = _validate_open_call_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400
    if not is_community_admin(user_id, data["community_id"]):
        return jsonify({"error": "Forbidden."}), 403

    description = data.get("description")
    if isinstance(description, str):
        description = description.strip() or None

    oc = OpenCall(
        community_id=data["community_id"],
        title=data["title"],
        description=description,
    )
    db.session.add(oc)
    try:
        db.session.flush()
        _set_open_call_skills(oc, data.get("skill_ids"))
        db.session.commit()
        return jsonify({"message": "Open call created.", "open_call": oc.to_dict(include_skills=True)}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to create open call."}), 500


def get_open_calls(community_id=None):
    query = OpenCall.query
    if community_id:
        query = query.filter_by(community_id=community_id)
    items = query.all()
    return jsonify({"open_calls": [o.to_dict(include_skills=True) for o in items]}), 200


def get_open_call(open_call_id):
    oc = OpenCall.query.get(open_call_id)
    if not oc:
        return jsonify({"error": "Open call not found."}), 404
    return jsonify({"open_call": oc.to_dict(include_skills=True)}), 200


def update_open_call(open_call_id, data, user_id):
    oc = OpenCall.query.get(open_call_id)
    if not oc:
        return jsonify({"error": "Open call not found."}), 404
    if not is_community_admin(user_id, oc.community_id):
        return jsonify({"error": "Forbidden."}), 403
    if "title" in data:
        oc.title = data["title"]
    if "description" in data:
        description = data.get("description")
        oc.description = (
            description.strip() if isinstance(description, str) and description.strip() else None
        )
    if "status" in data:
        oc.status = data["status"]
    if "skill_ids" in data:
        _set_open_call_skills(oc, data["skill_ids"])
    try:
        db.session.commit()
        return jsonify({"message": "Open call updated.", "open_call": oc.to_dict(include_skills=True)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update open call."}), 500


def delete_open_call(open_call_id, user_id):
    oc = OpenCall.query.get(open_call_id)
    if not oc:
        return jsonify({"error": "Open call not found."}), 404
    if not is_community_admin(user_id, oc.community_id):
        return jsonify({"error": "Forbidden."}), 403
    try:
        db.session.delete(oc)
        db.session.commit()
        return jsonify({"message": "Open call deleted."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete open call."}), 500
