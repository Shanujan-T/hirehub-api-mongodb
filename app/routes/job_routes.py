from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import ai_features_controller, job_controller
from app.middleware import roles_required

jobs_bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")


@jobs_bp.route("", methods=["GET"])
@jwt_required()
def list_jobs():
    return job_controller.get_jobs()


@jobs_bp.route("", methods=["POST"])
@roles_required("user")
def create_job():
    return job_controller.create_job()


@jobs_bp.route("/generate-description", methods=["POST"])
@roles_required("user")
def generate_job_description():
    return ai_features_controller.generate_job_description(
        int(get_jwt_identity()), request.get_json() or {}
    )


@jobs_bp.route("/suggested-price", methods=["GET"])
@roles_required("user")
def suggested_price():
    category = request.args.get("category", "")
    scope = request.args.get("scope", "")
    quantity = request.args.get("quantity")
    district = request.args.get("district", "")
    return job_controller.get_suggested_price(category, scope, quantity, district)



@jobs_bp.route("/<int:job_id>", methods=["GET"])
@jwt_required()
def get_job(job_id):
    return job_controller.get_job(job_id)


@jobs_bp.route("/<int:job_id>", methods=["PUT"])
@roles_required("user")
def update_job(job_id):
    return job_controller.update_job(job_id)


@jobs_bp.route("/<int:job_id>", methods=["DELETE"])
@roles_required("user")
def delete_job(job_id):
    return job_controller.delete_job(job_id)


@jobs_bp.route("/<int:job_id>/applications", methods=["GET"])
@roles_required("user")
def job_applications(job_id):
    return job_controller.get_job_applications(job_id)


@jobs_bp.route("/<int:job_id>/recommended-communities", methods=["GET"])
@roles_required("user")
def recommended_communities(job_id):
    return ai_features_controller.recommended_communities_for_job(
        job_id, int(get_jwt_identity())
    )


@jobs_bp.route("/<int:job_id>/suggest-bid", methods=["POST"])
@roles_required("employer")
def suggest_bid(job_id):
    return ai_features_controller.suggest_bid(
        job_id, int(get_jwt_identity()), request.get_json() or {}
    )


@jobs_bp.route("/<int:job_id>/invite", methods=["POST"])
@roles_required("user")
def invite_community(job_id):
    from app.controllers import community_application_controller

    data = request.get_json() or {}
    return community_application_controller.invite_community_to_job(
        job_id, data.get("community_id"), int(get_jwt_identity())
    )
