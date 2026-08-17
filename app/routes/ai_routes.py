from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import ai_concierge_controller

ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")


@ai_bp.route("/concierge", methods=["GET"])
@jwt_required()
def concierge_status():
    return ai_concierge_controller.concierge_meta()


@ai_bp.route("/concierge", methods=["POST"])
@jwt_required()
def concierge_ask():
    return ai_concierge_controller.ask_concierge(
        int(get_jwt_identity()), request.get_json() or {}
    )
