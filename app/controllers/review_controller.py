from flask import jsonify
from sqlalchemy import func

from app.extensions import db
from app.models.community_model import Community
from app.models.contract_model import Contract
from app.models.job_model import Job
from app.models.review_model import Review


def _validate_review_payload(data):
    errors = []
    if not data.get("contract_id"):
        errors.append("contract_id is required.")
    if not data.get("community_id"):
        errors.append("community_id is required.")
    rating = data.get("rating")
    if rating is None or not (1 <= int(rating) <= 5):
        errors.append("rating must be between 1 and 5.")
    return errors


def create_review(data, reviewer_id):
    errors = _validate_review_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400

    contract = Contract.query.get(data["contract_id"])
    if not contract:
        return jsonify({"error": "Contract not found."}), 404
    job = Job.query.get(contract.job_id)
    if not job or job.posted_by_id != reviewer_id:
        return jsonify({"error": "Forbidden."}), 403
    if contract.status != "completed":
        return jsonify({"error": "Contract must be completed to leave a review."}), 400

    review = Review(
        contract_id=data["contract_id"],
        reviewer_id=reviewer_id,
        community_id=data["community_id"],
        member_id=data.get("member_id"),
        rating=data["rating"],
        comment=data.get("comment"),
    )
    db.session.add(review)

    # Update community reputation
    avg = (
        db.session.query(func.avg(Review.rating))
        .filter(Review.community_id == data["community_id"])
        .scalar()
    )
    community = Community.query.get(data["community_id"])
    if community and avg:
        community.reputation_score = float(avg)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to create review."}), 500

    # Event-driven digest refresh (same pattern as category pricing recalc)
    try:
        from app.utils.review_digest_utils import recalc_review_digest

        recalc_review_digest(int(data["community_id"]))
    except Exception:
        pass

    return jsonify({"message": "Review created.", "review": review.to_dict()}), 201


def get_reviews(community_id=None, member_id=None):
    query = Review.query
    if community_id:
        query = query.filter_by(community_id=community_id)
    if member_id:
        query = query.filter_by(member_id=member_id)
    reviews = query.all()
    return jsonify({"reviews": [r.to_dict() for r in reviews]}), 200
