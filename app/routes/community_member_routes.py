from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import community_member_controller
from app.middleware import roles_required

community_members_bp = Blueprint("community_members", __name__, url_prefix="/api/community-members")


@community_members_bp.route("/my", methods=["GET"])
@roles_required("employer")
def my_memberships():
    return community_member_controller.get_my_memberships(int(get_jwt_identity()))


@community_members_bp.route("/join/<int:community_id>", methods=["POST"])
@roles_required("employer")
def join_community(community_id):
    return community_member_controller.request_join(community_id, int(get_jwt_identity()))


@community_members_bp.route("/community/<int:community_id>", methods=["GET"])
@roles_required("employer")
def list_members(community_id):
    status = request.args.get("status")
    return community_member_controller.get_community_members(community_id, status)


@community_members_bp.route("/<int:membership_id>/approve", methods=["POST"])
@roles_required("employer")
def approve_member(membership_id):
    return community_member_controller.approve_member(membership_id, int(get_jwt_identity()), "approve")


@community_members_bp.route("/<int:membership_id>/reject", methods=["POST"])
@roles_required("employer")
def reject_member(membership_id):
    return community_member_controller.approve_member(membership_id, int(get_jwt_identity()), "reject")


@community_members_bp.route("/<int:membership_id>", methods=["DELETE"])
@roles_required("employer")
def delete_member(membership_id):
    return community_member_controller.delete_community_member(membership_id, int(get_jwt_identity()))
