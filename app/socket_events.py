"""Socket.IO event handlers for contract conversations."""

from flask import request
from flask_jwt_extended import decode_token
from flask_socketio import join_room, leave_room

from app.controllers.conversation_controller import can_access_contract_conversation
from app.extensions import socketio
from app.models.conversation_model import Conversation
from app.models.user_model import User
from app.utils.notification_utils import user_room

_connected_users = {}


def _conversation_room(conversation_id):
    return f"conversation_{conversation_id}"


def _user_from_token(token):
    if not token:
        return None
    try:
        decoded = decode_token(token)
        user_id = int(decoded["sub"])
        return User.query.get(user_id)
    except Exception:
        return None


@socketio.on("connect")
def handle_connect(auth):
    token = None
    if isinstance(auth, dict):
        token = auth.get("token")
    if not token:
        token = request.args.get("token")
    user = _user_from_token(token)
    if not user:
        return False
    _connected_users[request.sid] = user.id
    join_room(user_room(user.id))


@socketio.on("disconnect")
def handle_disconnect():
    user_id = _connected_users.pop(request.sid, None)
    if user_id:
        leave_room(user_room(user_id))


@socketio.on("join_conversation")
def handle_join_conversation(data):
    user_id = _connected_users.get(request.sid)
    if not user_id:
        return {"error": "Unauthorized."}

    conversation_id = (data or {}).get("conversation_id")
    if not conversation_id:
        return {"error": "conversation_id is required."}

    conversation = Conversation.query.get(conversation_id)
    if not conversation:
        return {"error": "Conversation not found."}

    contract = conversation.contract
    if not contract or not can_access_contract_conversation(user_id, contract):
        return {"error": "Forbidden."}

    join_room(_conversation_room(conversation.id))
    return {"joined": _conversation_room(conversation.id)}


@socketio.on("leave_conversation")
def handle_leave_conversation(data):
    conversation_id = (data or {}).get("conversation_id")
    if not conversation_id:
        return {"error": "conversation_id is required."}
    leave_room(_conversation_room(conversation_id))
    return {"left": _conversation_room(conversation_id)}
