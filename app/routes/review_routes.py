from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import review_controller
from app.middleware import roles_required

reviews_bp = Blueprint("reviews", __name__, url_prefix="/api/reviews")


@reviews_bp.route("", methods=["GET"])
def list_reviews():
    community_id = request.args.get("community_id", type=int)
    member_id = request.args.get("member_id", type=int)
    return review_controller.get_reviews(community_id, member_id)


@reviews_bp.route("", methods=["POST"])
@roles_required("user")
def create_review():
    return review_controller.create_review(request.get_json() or {}, get_jwt_identity())
