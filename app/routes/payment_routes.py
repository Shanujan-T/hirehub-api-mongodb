from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import payment_controller
from app.models.user_model import User

payments_bp = Blueprint("payments", __name__, url_prefix="/api/payments")


@payments_bp.route("/my-earnings", methods=["GET"])
@jwt_required()
def my_earnings():
    user = User.query.get(int(get_jwt_identity()))
    return payment_controller.get_my_earnings(user.id, user.role)


@payments_bp.route("", methods=["GET"])
@jwt_required()
def list_payments():
    user = User.query.get(int(get_jwt_identity()))
    return payment_controller.get_payments(user.id, user.role)
