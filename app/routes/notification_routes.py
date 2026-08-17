from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import notification_controller

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@notifications_bp.route("", methods=["GET"])
@jwt_required()
def list_notifications():
    unread_only = request.args.get("unread") == "1"
    return notification_controller.list_notifications(int(get_jwt_identity()), unread_only)


@notifications_bp.route("/unread-count", methods=["GET"])
@jwt_required()
def unread_count():
    return notification_controller.unread_count(int(get_jwt_identity()))


@notifications_bp.route("/<int:notification_id>/read", methods=["PATCH", "PUT"])
@jwt_required()
def mark_read(notification_id):
    return notification_controller.mark_read(notification_id, int(get_jwt_identity()))


@notifications_bp.route("/read-all", methods=["PATCH", "PUT"])
@jwt_required()
def mark_all_read():
    return notification_controller.mark_all_read(int(get_jwt_identity()))
