from flask import jsonify
from flask_jwt_extended import create_access_token
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.user_model import User


def _validate_auth_payload(data, is_register=False):
    errors = []
    if is_register:
        if not data.get("email"):
            errors.append("email is required.")
        if not data.get("password"):
            errors.append("password is required.")
        if not data.get("full_name"):
            errors.append("full_name is required.")
        if data.get("role") not in {"user", "employer"}:
            errors.append("role is required and must be either user or employer.")
    else:
        if not data.get("email"):
            errors.append("email is required.")
        if not data.get("password"):
            errors.append("password is required.")
    return errors


def register(data):
    errors = _validate_auth_payload(data, is_register=True)
    if errors:
        return jsonify({"errors": errors}), 400

    email = str(data["email"]).strip().lower()
    full_name = str(data["full_name"]).strip()
    if not email or not full_name:
        return jsonify({"errors": ["email and full_name cannot be blank."]}), 400

    if User.query.filter(func.lower(User.email) == email).first():
        return jsonify({"error": "Email already registered."}), 409

    user = User(
        email=email,
        full_name=full_name,
        role=data["role"],
    )
    user.set_password(data["password"])
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Email already registered."}), 409
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Registration failed. Please try again."}), 500

    token = create_access_token(identity=str(user.id))
    return jsonify({
        "message": "Registered successfully.",
        "access_token": token,
        "user": user.to_dict(viewer_id=user.id, viewer_role=user.role, include_skills=True),
    }), 201


def login(data):
    errors = _validate_auth_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400

    email = str(data["email"]).strip().lower()
    user = User.query.filter(func.lower(User.email) == email).first()
    if not user or not user.check_password(data["password"]):
        return jsonify({"error": "Invalid email or password."}), 401

    if not user.is_active:
        return jsonify({"error": "Account suspended."}), 403

    token = create_access_token(identity=str(user.id))
    return jsonify({
        "access_token": token,
        "user": user.to_dict(viewer_id=user.id, viewer_role=user.role, include_skills=True),
    }), 200


def get_me(user_id):
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found."}), 404
    if not user.is_active:
        return jsonify({"error": "Account suspended."}), 403
    return jsonify({
        "user": user.to_dict(viewer_id=user.id, viewer_role=user.role, include_stats=True, include_skills=True),
    }), 200
