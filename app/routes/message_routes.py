from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import message_controller

messages_bp = Blueprint("messages", __name__, url_prefix="/api/messages")


@messages_bp.route("/<int:message_id>/delete-for-me", methods=["DELETE"])
@jwt_required()
def delete_message_for_me(message_id):
    return message_controller.delete_message_for_me(message_id, int(get_jwt_identity()))


@messages_bp.route("/<int:message_id>/delete-for-everyone", methods=["DELETE"])
@jwt_required()
def delete_message_for_everyone(message_id):
    return message_controller.delete_message_for_everyone(message_id, int(get_jwt_identity()))
