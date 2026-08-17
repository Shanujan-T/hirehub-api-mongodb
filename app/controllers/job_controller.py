from datetime import datetime

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import func

from app.extensions import db
from app.middleware import can_browse_job_marketplace
from app.models.category_model import Category
from app.models.community_application_model import CommunityApplication
from app.models.contract_model import Contract
from app.models.job_model import Job
from app.models.user_model import User
from app.utils import title_case_words
from app.utils.scope_utils import validate_scope_data


def _jobs_with_application_counts(jobs, *, include_poster=False):
    """Serialize jobs and attach CommunityApplication counts in one query."""
    if not jobs:
        return []
    ids = [j.id for j in jobs]
    rows = (
        db.session.query(CommunityApplication.job_id, func.count(CommunityApplication.id))
        .filter(CommunityApplication.job_id.in_(ids))
        .group_by(CommunityApplication.job_id)
        .all()
    )
    counts = {job_id: int(n) for job_id, n in rows}
    return [
        j.to_dict(include_poster=include_poster, application_count=counts.get(j.id, 0))
        for j in jobs
    ]


def create_job():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    required = ["category_id", "title", "description", "location", "deadline", "final_price"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    category = Category.query.get(data["category_id"])
    if not category or category.status != "approved":
        return jsonify({"error": "Invalid category."}), 400

    try:
        deadline = datetime.strptime(data["deadline"], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid deadline format. Use YYYY-MM-DD."}), 400

    event_time = None
    if category.name.strip().lower() == "photography":
        event_time_value = str(data.get("event_time") or "").strip()
        try:
            event_time = datetime.strptime(event_time_value, "%H:%M").time()
        except ValueError:
            return jsonify({"error": "Photography jobs require a valid event time (HH:MM)."}), 400

    scope_data, scope_errors = validate_scope_data(
        category.get_scope_schema(), data.get("scope_data")
    )
    if scope_errors:
        return jsonify({"error": scope_errors[0], "errors": scope_errors}), 400

    job = Job(
        posted_by_id=user_id,
        category_id=data["category_id"],
        title=title_case_words(data["title"]),
        description=data["description"],
        location=title_case_words(data["location"]),
        deadline=deadline,
        event_time=event_time,
        suggested_price=data.get("suggested_price"),
        final_price=data["final_price"],
        status="open",
    )
    job.set_scope_data(scope_data)
    db.session.add(job)
    db.session.commit()

    return jsonify({"message": "Job created.", "job": job.to_dict()}), 201


def get_jobs():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    marketplace = request.args.get("marketplace", "").lower() in ("1", "true", "yes")
    category_id = request.args.get("category_id", type=int)
    status = (request.args.get("status") or "").strip().lower() or None

    if marketplace:
        if not can_browse_job_marketplace(user_id):
            return (
                jsonify(
                    {
                        "error": "Job marketplace is available only to community admins "
                        "of communities with at least 3 approved members."
                    }
                ),
                403,
            )
        query = Job.query.filter_by(status="open")
        if category_id:
            query = query.filter_by(category_id=category_id)
        jobs = query.order_by(Job.created_at.desc()).all()
        return jsonify({"jobs": _jobs_with_application_counts(jobs, include_poster=True)}), 200

    if user and user.role == "admin":
        query = Job.query
        if category_id:
            query = query.filter_by(category_id=category_id)
        if status in ("open", "assigned", "closed"):
            query = query.filter_by(status=status)
        jobs = query.order_by(Job.created_at.desc()).all()
        return jsonify({"jobs": _jobs_with_application_counts(jobs, include_poster=True)}), 200

    # Current user's own jobs (employer / job poster). Optional filters for invite dialog.
    query = Job.query.filter_by(posted_by_id=user_id)
    if category_id:
        query = query.filter_by(category_id=category_id)
    if status in ("open", "assigned", "closed"):
        query = query.filter_by(status=status)
    jobs = query.order_by(Job.created_at.desc()).all()
    return jsonify({"jobs": _jobs_with_application_counts(jobs)}), 200


def get_job(job_id):
    user_id = int(get_jwt_identity())
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404

    if job.posted_by_id == user_id:
        return jsonify({"job": job.to_dict(include_poster=True)}), 200

    if job.status == "open" and can_browse_job_marketplace(user_id):
        return jsonify({"job": job.to_dict(include_poster=True)}), 200

    return jsonify({"error": "Forbidden."}), 403


def update_job(job_id):
    user_id = int(get_jwt_identity())
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.posted_by_id != user_id:
        return jsonify({"error": "Forbidden."}), 403
    if job.status != "open":
        return jsonify({"error": "Only open jobs can be updated."}), 400

    data = request.get_json() or {}
    for field in ("title", "description", "location", "final_price", "suggested_price"):
        if field in data:
            value = data[field]
            if field in ("title", "location") and isinstance(value, str):
                value = title_case_words(value)
            setattr(job, field, value)
    if "deadline" in data:
        try:
            job.deadline = datetime.strptime(data["deadline"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid deadline format."}), 400
    if "event_time" in data:
        event_time_value = str(data["event_time"] or "").strip()
        if not event_time_value:
            job.event_time = None
        else:
            try:
                job.event_time = datetime.strptime(event_time_value, "%H:%M").time()
            except ValueError:
                return jsonify({"error": "Invalid event time format. Use HH:MM."}), 400
    if "category_id" in data:
        category = Category.query.get(data["category_id"])
        if not category or category.status != "approved":
            return jsonify({"error": "Invalid category."}), 400
        job.category_id = data["category_id"]

    if "scope_data" in data or "category_id" in data:
        category = Category.query.get(job.category_id)
        scope_payload = data["scope_data"] if "scope_data" in data else job.get_scope_data()
        scope_data, scope_errors = validate_scope_data(
            category.get_scope_schema() if category else None,
            scope_payload,
        )
        if scope_errors:
            return jsonify({"error": scope_errors[0], "errors": scope_errors}), 400
        job.set_scope_data(scope_data)

    db.session.commit()
    return jsonify({"message": "Job updated.", "job": job.to_dict()}), 200


def delete_job(job_id):
    user_id = int(get_jwt_identity())
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.posted_by_id != user_id:
        return jsonify({"error": "Forbidden."}), 403
    if job.status != "open":
        return jsonify({"error": "Only open jobs can be deleted."}), 400

    db.session.delete(job)
    db.session.commit()
    return jsonify({"message": "Job deleted."}), 200


def get_job_applications(job_id):
    user_id = int(get_jwt_identity())
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    if job.posted_by_id != user_id:
        return jsonify({"error": "Forbidden."}), 403

    applications = (
        CommunityApplication.query.filter_by(job_id=job_id)
        .order_by(CommunityApplication.created_at.desc())
        .all()
    )
    return jsonify({"applications": [a.to_dict(include_community=True) for a in applications]}), 200


def get_suggested_price(category, scope, quantity, district):
    from app.utils.pricing_utils import suggest_price

    qty = 1
    if quantity:
        try:
            qty = float(quantity)
            if qty.is_integer():
                qty = int(qty)
        except ValueError:
            qty = 1

    price = suggest_price(category, qty, district, scope)
    return jsonify({"suggestedPrice": price}), 200
