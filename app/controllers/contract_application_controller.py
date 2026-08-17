from flask import jsonify

from app.extensions import db
from app.middleware import is_community_admin
from app.models.community_member_model import CommunityMember
from app.models.contract_application_model import ContractApplication
from app.models.contract_model import Contract


def apply_to_contract(contract_id, user_id, data):
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404
    if contract.status != "open_internally":
        return jsonify({"error": "Contract is not open for internal applications."}), 400

    membership = CommunityMember.query.filter_by(
        community_id=contract.community_id,
        user_id=user_id,
        status="approved",
    ).first()
    if not membership:
        return jsonify({"error": "Must be an approved community member."}), 403

    existing = ContractApplication.query.filter_by(
        contract_id=contract_id, member_id=user_id
    ).first()
    if existing:
        return jsonify({"error": "Already applied to this contract."}), 409

    application = ContractApplication(
        contract_id=contract_id,
        member_id=user_id,
        note=data.get("note"),
        status="applied",
    )
    db.session.add(application)
    try:
        db.session.commit()
        return jsonify({"message": "Applied to contract.", "contract_application": application.to_dict()}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to apply to contract."}), 500


def get_contract_applications(contract_id, user_id):
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({"error": "Contract not found."}), 404
    if not is_community_admin(user_id, contract.community_id):
        return jsonify({"error": "Forbidden."}), 403

    applications = ContractApplication.query.filter_by(contract_id=contract_id).all()
    return jsonify({
        "contract_applications": [a.to_dict(include_member=True) for a in applications]
    }), 200


def get_my_contract_applications(user_id):
    applications = ContractApplication.query.filter_by(member_id=user_id).all()
    return jsonify({"contract_applications": [a.to_dict() for a in applications]}), 200
