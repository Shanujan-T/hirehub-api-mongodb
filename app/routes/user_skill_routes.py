from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import user_skill_controller, work_sample_controller
from app.middleware import roles_required

user_skills_bp = Blueprint("user_skills", __name__, url_prefix="/api/user-skills")


@user_skills_bp.route("", methods=["GET"])
@roles_required("employer")
def list_user_skills():
    user_id = request.args.get("user_id", type=int)
    return user_skill_controller.get_user_skills(user_id)


@user_skills_bp.route("", methods=["POST"])
@roles_required("employer")
def create_user_skill():
    return user_skill_controller.create_user_skill(request.get_json() or {})


@user_skills_bp.route("/<int:user_skill_id>", methods=["GET"])
@roles_required("employer")
def get_user_skill(user_skill_id):
    return user_skill_controller.get_user_skill(user_skill_id)


@user_skills_bp.route("/<int:user_skill_id>", methods=["PUT"])
@roles_required("employer")
def update_user_skill(user_skill_id):
    return user_skill_controller.update_user_skill(user_skill_id, request.get_json() or {})


@user_skills_bp.route("/<int:user_skill_id>", methods=["DELETE"])
@roles_required("employer")
def delete_user_skill(user_skill_id):
    return user_skill_controller.delete_user_skill(user_skill_id)


@user_skills_bp.route("/<int:user_skill_id>/work-samples", methods=["GET"])
@roles_required("employer")
def list_work_samples(user_skill_id):
    return work_sample_controller.list_work_samples(user_skill_id, int(get_jwt_identity()))


@user_skills_bp.route("/<int:user_skill_id>/work-samples", methods=["POST"])
@roles_required("employer")
def create_work_sample(user_skill_id):
    return work_sample_controller.create_work_sample(user_skill_id, int(get_jwt_identity()))
