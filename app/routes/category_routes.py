from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import category_controller
from app.middleware import roles_required

categories_bp = Blueprint("categories", __name__, url_prefix="/api/categories")


@categories_bp.route("", methods=["GET"])
def list_categories():
    return category_controller.get_categories()


@categories_bp.route("", methods=["POST"])
@roles_required("admin")
def create_category():
    return category_controller.create_category(request.get_json() or {})


@categories_bp.route("/request", methods=["POST"])
@jwt_required()
def request_category():
    return category_controller.request_category(
        int(get_jwt_identity()), request.get_json() or {}
    )


@categories_bp.route("/<int:category_id>/pricing-suggestion", methods=["GET"])
def pricing_suggestion(category_id):
    location = request.args.get("location", "")
    deadline = request.args.get("deadline", "")
    return category_controller.pricing_suggestion(category_id, location, deadline=deadline)


@categories_bp.route("/<int:category_id>/seed-pricing", methods=["POST"])
@roles_required("admin")
def seed_pricing(category_id):
    return category_controller.seed_category_pricing(category_id, request.get_json() or {})


@categories_bp.route("/<int:category_id>/seed-district-pricing", methods=["POST"])
@roles_required("admin")
def seed_district_pricing(category_id):
    return category_controller.seed_district_pricing_for_category(category_id)


@categories_bp.route("/seed-district-pricing", methods=["POST"])
@roles_required("admin")
def seed_all_district_pricing():
    return category_controller.seed_all_district_pricing()


@categories_bp.route("/<int:category_id>/recalc-pricing", methods=["POST"])
@roles_required("admin")
def recalc_pricing(category_id):
    location = request.args.get("location", "")
    return category_controller.recalc_pricing(category_id, location)


@categories_bp.route("/<int:category_id>/approve", methods=["POST"])
@roles_required("admin")
def approve_category(category_id):
    return category_controller.approve_category(category_id, request.get_json() or {})


@categories_bp.route("/<int:category_id>/reject", methods=["POST"])
@roles_required("admin")
def reject_category(category_id):
    return category_controller.reject_category(category_id, request.get_json() or {})


@categories_bp.route("/<int:category_id>", methods=["GET"])
def get_category(category_id):
    return category_controller.get_category(category_id)


@categories_bp.route("/<int:category_id>", methods=["PUT"])
@roles_required("admin")
def update_category(category_id):
    return category_controller.update_category(category_id, request.get_json() or {})


@categories_bp.route("/<int:category_id>", methods=["DELETE"])
@roles_required("admin")
def delete_category(category_id):
    return category_controller.delete_category(category_id)
