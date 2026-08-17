from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import contract_application_controller

contract_applications_bp = Blueprint(
    "contract_applications", __name__, url_prefix="/api/contract-applications"
)


@contract_applications_bp.route("/my", methods=["GET"])
@jwt_required()
def my_applications():
    return contract_application_controller.get_my_contract_applications(get_jwt_identity())


@contract_applications_bp.route("/apply", methods=["POST"])
@jwt_required()
def apply_to_contract():
    data = request.get_json() or {}
    return contract_application_controller.apply_to_contract(
        data.get("contract_id"), get_jwt_identity(), data
    )


@contract_applications_bp.route("/contract/<int:contract_id>", methods=["GET"])
@jwt_required()
def contract_applications(contract_id):
    return contract_application_controller.get_contract_applications(
        contract_id, get_jwt_identity()
    )
