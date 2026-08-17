from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import ai_features_controller, contract_controller, message_controller
from app.models.user_model import User

contracts_bp = Blueprint("contracts", __name__, url_prefix="/api/contracts")


def _current_user():
    user = User.query.get(int(get_jwt_identity()))
    return user.id, user.role


@contracts_bp.route("", methods=["GET"])
@jwt_required()
def list_contracts():
    user_id, user_role = _current_user()
    return contract_controller.get_contracts(user_id, user_role)


@contracts_bp.route("/needs-attention", methods=["GET"])
@jwt_required()
def contracts_needing_attention():
    user_id, user_role = _current_user()
    return contract_controller.get_contracts_needing_attention(user_id, user_role)


@contracts_bp.route("/<int:contract_id>", methods=["GET"])
@jwt_required()
def get_contract(contract_id):
    user_id, user_role = _current_user()
    return contract_controller.get_contract(contract_id, user_id, user_role)


@contracts_bp.route("/<int:contract_id>/open-internally", methods=["POST"])
@jwt_required()
def open_internally(contract_id):
    return contract_controller.open_contract_internally(contract_id, get_jwt_identity())


@contracts_bp.route("/<int:contract_id>/select-member", methods=["POST"])
@jwt_required()
def select_member(contract_id):
    data = request.get_json() or {}
    return contract_controller.select_member(
        contract_id, data.get("application_id"), get_jwt_identity()
    )


@contracts_bp.route("/<int:contract_id>/select-members", methods=["POST"])
@jwt_required()
def select_members(contract_id):
    data = request.get_json() or {}
    return contract_controller.select_members(
        contract_id, data.get("selections", []), get_jwt_identity()
    )


@contracts_bp.route("/<int:contract_id>/submit-deliverable", methods=["POST"])
@jwt_required()
def submit_deliverable(contract_id):
    return contract_controller.submit_deliverable(
        contract_id, get_jwt_identity(), request.get_json() or {}
    )


@contracts_bp.route("/<int:contract_id>/admin-approve-deliverable", methods=["POST"])
@jwt_required()
def admin_approve_deliverable(contract_id):
    return contract_controller.approve_deliverable_admin(contract_id, get_jwt_identity())


@contracts_bp.route("/<int:contract_id>/ai-review-deliverable", methods=["POST"])
@jwt_required()
def ai_review_deliverable(contract_id):
    return ai_features_controller.ai_review_deliverable(
        contract_id, int(get_jwt_identity())
    )


@contracts_bp.route("/<int:contract_id>/poster-approve-deliverable", methods=["POST"])
@jwt_required()
def poster_approve_deliverable(contract_id):
    return contract_controller.approve_deliverable_poster(contract_id, int(get_jwt_identity()))


@contracts_bp.route("/<int:contract_id>/client-approve-deliverable", methods=["POST"])
@jwt_required()
def client_approve_deliverable_legacy(contract_id):
    return contract_controller.approve_deliverable_poster(contract_id, int(get_jwt_identity()))


@contracts_bp.route("/<int:contract_id>/messages", methods=["GET"])
@jwt_required()
def list_contract_messages(contract_id):
    return message_controller.list_messages(contract_id, int(get_jwt_identity()))


@contracts_bp.route("/<int:contract_id>/messages", methods=["POST"])
@jwt_required()
def send_contract_message(contract_id):
    return message_controller.send_message(
        contract_id, int(get_jwt_identity()), request.get_json() or {}
    )


@contracts_bp.route("/<int:contract_id>/messages/suggest-reply", methods=["POST"])
@jwt_required()
def suggest_contract_reply(contract_id):
    return message_controller.suggest_reply(contract_id, int(get_jwt_identity()))
