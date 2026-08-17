from flask import Blueprint, request, jsonify

from flask_jwt_extended import get_jwt_identity, jwt_required



from app.controllers import user_controller

from app.middleware import roles_required

from app.models.user_model import User



users_bp = Blueprint("users", __name__, url_prefix="/api/users")





@users_bp.route("", methods=["GET"])

@roles_required("admin")

def list_users():

    return user_controller.get_users()





@users_bp.route("/me/nic-document", methods=["POST"])

@jwt_required()

def upload_nic_document():

    user_id = int(get_jwt_identity())

    file_storage = request.files.get("document")

    return user_controller.upload_nic_document(user_id, file_storage)





@users_bp.route("/me/identity-verification", methods=["POST"])

@jwt_required()

def submit_identity_verification():

    user_id = int(get_jwt_identity())

    return user_controller.submit_identity_verification(user_id, request.get_json() or {})


@users_bp.route("/me/identity-verification/phone/send", methods=["POST"])
@jwt_required()
def send_identity_phone_otp():
    user_id = int(get_jwt_identity())
    return user_controller.send_identity_phone_otp(user_id, request.get_json() or {})


@users_bp.route("/me/identity-verification/phone/confirm", methods=["POST"])
@jwt_required()
def confirm_identity_phone_otp():
    user_id = int(get_jwt_identity())
    return user_controller.confirm_identity_phone_otp(user_id, request.get_json() or {})


@users_bp.route("/me/identity-verification/email/send", methods=["POST"])
@jwt_required()
def send_identity_email_otp():
    user_id = int(get_jwt_identity())
    return user_controller.send_identity_email_otp(user_id)


@users_bp.route("/me/identity-verification/email/confirm", methods=["POST"])
@jwt_required()
def confirm_identity_email_otp():
    user_id = int(get_jwt_identity())
    return user_controller.confirm_identity_email_otp(user_id, request.get_json() or {})


@users_bp.route("/<int:user_id>", methods=["GET"])

@jwt_required()

def get_user(user_id):

    current = User.query.get(int(get_jwt_identity()))

    return user_controller.get_user(user_id, current.id, current.role)





@users_bp.route("/<int:user_id>", methods=["PUT"])

@jwt_required()

def update_user(user_id):

    current = User.query.get(int(get_jwt_identity()))

    return user_controller.update_user(

        user_id, request.get_json() or {}, current.id, current.role

    )





@users_bp.route("/<int:user_id>/avatar", methods=["POST"])

@jwt_required()

def upload_avatar(user_id):

    current = User.query.get(int(get_jwt_identity()))

    file_storage = request.files.get("image")

    return user_controller.upload_avatar(user_id, current.id, current.role, file_storage)


@users_bp.route("/<int:user_id>/avatar", methods=["DELETE"])
@jwt_required()
def delete_avatar(user_id):
    current = User.query.get(int(get_jwt_identity()))
    return user_controller.delete_avatar(user_id, current.id, current.role)





@users_bp.route("/<int:user_id>/identity-verification/review", methods=["PUT"])

@roles_required("admin")

def review_identity_verification(user_id):

    return user_controller.verify_identity(user_id, request.get_json() or {})





@users_bp.route("/<int:user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    return user_controller.delete_user(user_id, get_jwt_identity())


@users_bp.route("/me/skills", methods=["GET"])
@jwt_required()
def get_my_skills():
    user_id = int(get_jwt_identity())
    from app.controllers import user_skill_controller
    return user_skill_controller.get_user_skills(user_id)


@users_bp.route("/me/skills", methods=["POST"])
@jwt_required()
def create_my_skill():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    data["user_id"] = user_id
    from app.controllers import user_skill_controller
    return user_skill_controller.create_user_skill(data)


@users_bp.route("/me/skills/<int:user_skill_id>", methods=["PUT"])
@jwt_required()
def update_my_skill(user_skill_id):
    user_id = int(get_jwt_identity())
    from app.models.user_skill_model import UserSkill
    us = UserSkill.query.get(user_skill_id)
    if not us:
        return jsonify({"error": "User skill not found."}), 404
    if us.user_id != user_id:
        return jsonify({"error": "Unauthorized to update this skill."}), 403
    from app.controllers import user_skill_controller
    return user_skill_controller.update_user_skill(user_skill_id, request.get_json() or {})


@users_bp.route("/me/skills/<int:user_skill_id>", methods=["DELETE"])
@jwt_required()
def delete_my_skill(user_skill_id):
    user_id = int(get_jwt_identity())
    from app.models.user_skill_model import UserSkill
    us = UserSkill.query.get(user_skill_id)
    if not us:
        return jsonify({"error": "User skill not found."}), 404
    if us.user_id != user_id:
        return jsonify({"error": "Unauthorized to delete this skill."}), 403
    from app.controllers import user_skill_controller
    return user_skill_controller.delete_user_skill(user_skill_id)

