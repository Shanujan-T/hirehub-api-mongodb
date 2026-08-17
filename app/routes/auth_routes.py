from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import auth_controller

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    return auth_controller.register(request.get_json() or {})


@auth_bp.route("/login", methods=["POST"])
def login():
    return auth_controller.login(request.get_json() or {})


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    return auth_controller.get_me(get_jwt_identity())
