from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import ai_features_controller, open_call_controller

open_calls_bp = Blueprint("open_calls", __name__, url_prefix="/api/open-calls")


@open_calls_bp.route("", methods=["GET"])
def list_open_calls():
    community_id = request.args.get("community_id", type=int)
    return open_call_controller.get_open_calls(community_id)


@open_calls_bp.route("/generate-description", methods=["POST"])
@jwt_required()
def generate_open_call_description():
    return ai_features_controller.generate_open_call_description(
        int(get_jwt_identity()), request.get_json() or {}
    )


@open_calls_bp.route("", methods=["POST"])
@jwt_required()
def create_open_call():
    return open_call_controller.create_open_call(request.get_json() or {}, get_jwt_identity())


@open_calls_bp.route("/<int:open_call_id>", methods=["GET"])
def get_open_call(open_call_id):
    return open_call_controller.get_open_call(open_call_id)


@open_calls_bp.route("/<int:open_call_id>", methods=["PUT"])
@jwt_required()
def update_open_call(open_call_id):
    return open_call_controller.update_open_call(
        open_call_id, request.get_json() or {}, get_jwt_identity()
    )


@open_calls_bp.route("/<int:open_call_id>", methods=["DELETE"])
@jwt_required()
def delete_open_call(open_call_id):
    return open_call_controller.delete_open_call(open_call_id, get_jwt_identity())
