import json
import logging

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from sqlalchemy import func

from app.extensions import db
from app.models.category_model import Category
from app.models.category_pricing_model import CategoryPricing
from app.models.user_model import User
from app.utils import utc_now
from app.utils.pricing_utils import (
    get_pricing_suggestion,
    recalc_category_pricing,
    seed_district_pricing,
)
from app.utils.scope_utils import normalize_scope_schema

logger = logging.getLogger(__name__)


def _find_by_name_ci(name: str):
    return Category.query.filter(func.lower(Category.name) == name.strip().lower()).first()


def _optional_admin_user():
    verify_jwt_in_request(optional=True)
    identity = get_jwt_identity()
    if not identity:
        return None
    user = User.query.get(int(identity))
    if user and user.role == "admin":
        return user
    return None


def _validate_category_payload(data, *, require_name=True, cat=None):
    errors = []
    if require_name and not data.get("name"):
        errors.append("name is required.")
    # scope_fields is an accepted alias for scope_schema
    incoming_schema = None
    if "scope_schema" in data or "scope_fields" in data:
        raw_schema = data.get("scope_schema", data.get("scope_fields"))
        normalized, schema_errors = normalize_scope_schema(raw_schema)
        errors.extend(schema_errors)
        incoming_schema = normalized

    key_to_check = None
    if "baseline_scope_key" in data:
        key_to_check = data.get("baseline_scope_key")
    elif cat is not None and cat.baseline_scope_key:
        if "scope_schema" in data or "scope_fields" in data:
            key_to_check = cat.baseline_scope_key

    if key_to_check not in (None, ""):
        key = str(key_to_check).strip()
        if incoming_schema is not None:
            schema = incoming_schema
        elif cat is not None:
            schema = cat.get_scope_schema() or []
        else:
            schema = []
        
        field = next((f for f in schema if isinstance(f, dict) and f.get("key") == key), None)
        if not field:
            errors.append(f"baseline_scope_key '{key}' does not exist in the category's scope schema.")
        elif field.get("type") != "number":
            errors.append(f"baseline_scope_key '{key}' must refer to a numeric field.")

    if "baseline_price" in data and data.get("baseline_price") not in (None, ""):
        try:
            price = float(data["baseline_price"])
            if price < 0:
                errors.append("baseline_price must be >= 0.")
        except (TypeError, ValueError):
            errors.append("baseline_price must be a number.")
    return errors


def _scope_payload(data: dict):
    """Prefer scope_schema; accept scope_fields as alias."""
    if "scope_schema" in data:
        return data.get("scope_schema")
    if "scope_fields" in data:
        return data.get("scope_fields")
    return None


def _apply_baseline_fields(cat: Category, data: dict) -> bool:
    """Apply baseline fields. Returns True if baseline_price or baseline_scope_key changed."""
    baseline_changed = False
    if "baseline_price" in data:
        raw = data.get("baseline_price")
        new_price = None if raw in (None, "") else float(raw)
        old = float(cat.baseline_price) if cat.baseline_price is not None else None
        if new_price != old:
            baseline_changed = True
        cat.baseline_price = new_price
    if "baseline_scope_key" in data:
        raw_key = data.get("baseline_scope_key")
        new_key = None if raw_key in (None, "") else str(raw_key).strip()
        if new_key != cat.baseline_scope_key:
            baseline_changed = True
        cat.baseline_scope_key = new_key
    return baseline_changed

def create_category(data):
    """Admin-created categories are approved immediately."""
    errors = _validate_category_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400
    name = str(data["name"]).strip()
    if _find_by_name_ci(name):
        return jsonify({"error": "Category already exists."}), 409

    schema, _ = normalize_scope_schema(_scope_payload(data) if ("scope_schema" in data or "scope_fields" in data) else None)
    cat = Category(
        name=name,
        status="approved",
        requested_by_id=None,
        request_description=None,
        rejection_reason=None,
    )
    cat.set_scope_schema(schema)
    _apply_baseline_fields(cat, data)
    db.session.add(cat)
    try:
        db.session.commit()
        if cat.baseline_price is not None:
            seed_district_pricing(cat.id)
        return jsonify({"message": "Category created.", "category": cat.to_dict()}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to create category."}), 500


def request_category(user_id: int, data: dict):
    """Any authenticated user can request a new category (pending until admin approves)."""
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required."}), 400
    if len(name) < 2:
        return jsonify({"error": "name must be at least 2 characters."}), 400
    if len(name) > 255:
        return jsonify({"error": "name is too long."}), 400

    if _find_by_name_ci(name):
        return (
            jsonify(
                {
                    "error": "A category with this name already exists or is pending review.",
                }
            ),
            409,
        )

    description = str(data.get("description") or data.get("request_description") or "").strip()
    if len(description) > 1000:
        return jsonify({"error": "description is too long (max 1000 chars)."}), 400

    cat = Category(
        name=name,
        status="pending",
        requested_by_id=user_id,
        request_description=description or None,
        rejection_reason=None,
    )
    db.session.add(cat)
    try:
        db.session.commit()
        return (
            jsonify(
                {
                    "message": "Your category request is pending admin review.",
                    "category": cat.to_dict(),
                }
            ),
            201,
        )
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to submit category request."}), 500


def get_categories():
    """
    Public/default: approved only.
    Admin may pass ?status=pending|approved|rejected|all for moderation.
    """
    status = (request.args.get("status") or "approved").strip().lower()
    admin = _optional_admin_user()

    if status != "approved":
        if not admin:
            return jsonify({"error": "Admin access required."}), 403
        query = Category.query
        if status == "all":
            pass
        elif status in ("pending", "approved", "rejected"):
            query = query.filter_by(status=status)
        else:
            return jsonify({"error": "Invalid status filter."}), 400
        categories = query.order_by(Category.created_at.desc()).all()
        return (
            jsonify(
                {
                    "categories": [
                        c.to_dict(include_requester=True) for c in categories
                    ]
                }
            ),
            200,
        )

    categories = (
        Category.query.filter_by(status="approved")
        .order_by(Category.name.asc())
        .all()
    )
    return jsonify({"categories": [c.to_dict() for c in categories]}), 200


def get_category(category_id):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    if cat.status != "approved":
        admin = _optional_admin_user()
        if not admin:
            return jsonify({"error": "Category not found."}), 404
        return jsonify({"category": cat.to_dict(include_requester=True)}), 200
    return jsonify({"category": cat.to_dict()}), 200


def update_category(category_id, data):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    errors = _validate_category_payload(data, require_name=False, cat=cat)
    if errors:
        return jsonify({"errors": errors}), 400
    if "name" in data:
        new_name = str(data["name"]).strip()
        existing = _find_by_name_ci(new_name)
        if existing and existing.id != cat.id:
            return jsonify({"error": "Category already exists."}), 409
        cat.name = new_name
    if "scope_schema" in data or "scope_fields" in data:
        schema, _ = normalize_scope_schema(_scope_payload(data))
        cat.set_scope_schema(schema)
    baseline_changed = _apply_baseline_fields(cat, data)
    try:
        db.session.commit()
        seed_stats = None
        if baseline_changed and cat.baseline_price is not None:
            seed_stats = seed_district_pricing(cat.id)
        payload = {
            "message": "Category updated.",
            "category": cat.to_dict(),
        }
        if seed_stats is not None:
            payload["district_pricing_seed"] = seed_stats
        return jsonify(payload), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update category."}), 500


def approve_category(category_id, data: dict):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    if cat.status != "pending":
        return jsonify({"error": "Only pending category requests can be approved."}), 400

    if "scope_schema" in data or "scope_fields" in data:
        schema, schema_errors = normalize_scope_schema(_scope_payload(data))
        if schema_errors:
            return jsonify({"errors": schema_errors}), 400
        cat.set_scope_schema(schema)

    cat.status = "approved"
    cat.rejection_reason = None
    _apply_baseline_fields(cat, data)
    try:
        db.session.commit()
        if cat.baseline_price is not None:
            seed_district_pricing(cat.id)
        return (
            jsonify(
                {
                    "message": "Category approved.",
                    "category": cat.to_dict(include_requester=True),
                }
            ),
            200,
        )
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to approve category."}), 500


def reject_category(category_id, data: dict):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    if cat.status != "pending":
        return jsonify({"error": "Only pending category requests can be rejected."}), 400

    reason = str(data.get("reason") or data.get("rejection_reason") or "").strip()
    cat.status = "rejected"
    cat.rejection_reason = reason or None
    try:
        db.session.commit()
        return (
            jsonify(
                {
                    "message": "Category rejected.",
                    "category": cat.to_dict(include_requester=True),
                }
            ),
            200,
        )
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to reject category."}), 500


def delete_category(category_id):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    try:
        db.session.delete(cat)
        db.session.commit()
        return jsonify({"message": "Category deleted."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to delete category."}), 500


def pricing_suggestion(category_id, location, scope_data=None, deadline=None):
    cat = Category.query.get(category_id)
    if not cat or cat.status != "approved":
        return jsonify({"error": "Category not found."}), 404

    if scope_data is None:
        # Prefer generic scope_values; keep scope_data for backward compatibility.
        raw = request.args.get("scope_values") or request.args.get("scope_data")
        if raw:
            try:
                scope_data = json.loads(raw)
            except json.JSONDecodeError:
                logger.exception("[suggested-price] could not parse scope query data: %r", raw)
                scope_data = None

    logger.info(
        "[suggested-price] request received category_id=%s location=%r deadline=%r scope_data=%s",
        category_id, location, deadline, scope_data,
    )

    result = get_pricing_suggestion(
        category_id,
        location,
        scope_data=scope_data,
        scope_schema=cat.get_scope_schema(),
        deadline=deadline,
    )
    return jsonify(result), 200


def seed_category_pricing(category_id, data):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    location = data.get("location")
    average_price = data.get("average_price", 0)
    sample_size = data.get("sample_size", 0)
    if not location:
        return jsonify({"errors": ["location is required."]}), 400

    pricing = CategoryPricing.query.filter_by(category_id=category_id, location=location).first()
    if pricing:
        if pricing.sample_size > 0 and not data.get("force"):
            return jsonify({
                "error": "This location already has real contract pricing. "
                "Pass force=true to overwrite, or use seed-district-pricing for estimates only."
            }), 409
        pricing.average_price = average_price
        pricing.sample_size = sample_size
        pricing.is_seeded_estimate = sample_size == 0
        pricing.last_updated = utc_now()
    else:
        pricing = CategoryPricing(
            category_id=category_id,
            location=location,
            average_price=average_price,
            sample_size=sample_size,
            is_seeded_estimate=sample_size == 0,
            last_updated=utc_now(),
        )
        db.session.add(pricing)
    try:
        db.session.commit()
        return jsonify({"message": "Pricing seeded.", "category_pricing": pricing.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to seed pricing."}), 500


def seed_district_pricing_for_category(category_id):
    """Admin: re-seed all 25 district estimate rows from category.baseline_price."""
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    if cat.baseline_price is None:
        return jsonify({
            "error": "Set a baseline_price (Tier-1 Colombo base) before seeding district pricing."
        }), 400
    stats = seed_district_pricing(category_id)
    return jsonify({
        "message": "District pricing estimates updated for seeded rows only "
        "(real sample_size > 0 rows were left untouched).",
        "stats": stats,
    }), 200


def seed_all_district_pricing():
    """Admin: seed district estimates for every approved category with a baseline."""
    stats = seed_district_pricing()
    return jsonify({
        "message": "District pricing estimates seeded for all categories with a baseline price.",
        "stats": stats,
    }), 200


def recalc_pricing(category_id, location):
    cat = Category.query.get(category_id)
    if not cat:
        return jsonify({"error": "Category not found."}), 404
    pricing = recalc_category_pricing(category_id, location)
    return jsonify({"message": "Pricing recalculated.", "category_pricing": pricing.to_dict()}), 200
