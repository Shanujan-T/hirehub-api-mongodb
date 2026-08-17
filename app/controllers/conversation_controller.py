from flask import jsonify

from app.middleware import is_community_admin
from app.models.contract_model import Contract
from app.models.conversation_model import Conversation
from app.models.job_model import Job


def _get_contract(contract_id):
    return Contract.query.get(contract_id)


def can_access_contract_conversation(user_id, contract):
    job = Job.query.get(contract.job_id)
    if job and job.posted_by_id == user_id:
        return True
    return is_community_admin(user_id, contract.community_id)


def get_conversation_for_contract(contract_id, user_id):
    contract = _get_contract(contract_id)
    if not contract:
        return None, (jsonify({"error": "Contract not found."}), 404)
    if not can_access_contract_conversation(user_id, contract):
        return None, (jsonify({"error": "Forbidden."}), 403)

    conversation = Conversation.query.filter_by(contract_id=contract_id).first()
    if not conversation:
        return None, (jsonify({"error": "Conversation not found for this contract."}), 404)

    return conversation, None
