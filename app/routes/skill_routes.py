from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.controllers import skill_controller
from app.middleware import roles_required

skills_bp = Blueprint("skills", __name__, url_prefix="/api/skills")


@skills_bp.route("", methods=["GET"])
def list_skills():
    return skill_controller.get_skills()


@skills_bp.route("", methods=["POST"])
@roles_required("admin")
def create_skill():
    return skill_controller.create_skill(request.get_json() or {})


@skills_bp.route("/<int:skill_id>", methods=["GET"])
def get_skill(skill_id):
    return skill_controller.get_skill(skill_id)


@skills_bp.route("/<int:skill_id>", methods=["PUT"])
@roles_required("admin")
def update_skill(skill_id):
    return skill_controller.update_skill(skill_id, request.get_json() or {})


@skills_bp.route("/<int:skill_id>", methods=["DELETE"])
@roles_required("admin")
def delete_skill(skill_id):
    return skill_controller.delete_skill(skill_id)
