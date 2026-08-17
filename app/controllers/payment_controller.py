from flask import jsonify

from app.middleware import get_admin_community_ids, is_community_admin
from app.models.contract_model import Contract
from app.models.job_model import Job
from app.models.payment_model import Payment


def get_payments(user_id, user_role):
    if user_role == "admin":
        payments = Payment.query.all()
        return jsonify({"payments": [p.to_dict() for p in payments]}), 200

    seen = set()
    payments = []

    def add_batch(batch):
        for p in batch:
            if p.id not in seen:
                seen.add(p.id)
                payments.append(p)

    add_batch(
        Payment.query.join(Contract).join(Job).filter(Job.posted_by_id == user_id).all()
    )

    admin_ids = get_admin_community_ids(user_id)
    if admin_ids:
        add_batch(
            Payment.query.join(Contract).filter(Contract.community_id.in_(admin_ids)).all()
        )

    add_batch(
        Payment.query.join(Contract).filter(Contract.assigned_member_id == user_id).all()
    )

    return jsonify({"payments": [p.to_dict() for p in payments]}), 200


def get_my_earnings(user_id, user_role):
    return get_payments(user_id, user_role)
