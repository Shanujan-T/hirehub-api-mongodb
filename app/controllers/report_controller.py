import logging
from datetime import timedelta

from flask import jsonify

from app.extensions import db
from app.models.community_model import Community
from app.models.report_model import (
    REPORT_REASONS,
    REPORT_STATUSES,
    REPORT_TARGET_TYPES,
    Report,
)
from app.models.user_model import User
from app.utils import utc_now
from app.utils.email_client import send_transactional_email

logger = logging.getLogger(__name__)
MAX_REPORTS_PER_24_HOURS = 5


def _errors(messages):
    return jsonify({"errors": messages}), 400


def _target_exists(target_type, target_id):
    if target_type == "community":
        return db.session.get(Community, target_id) is not None
    user = db.session.get(User, target_id)
    if not user:
        return False
    return target_type == "user" or user.role == "employer"


def _notify_admins(report):
    recipients = [u.email for u in User.query.filter_by(role="admin", is_active=True).all()]
    if not recipients:
        return
    try:
        send_transactional_email(
            recipients,
            f"New HireHub report #{report.id}",
            f"<p>A new <strong>{report.reason}</strong> report was filed against "
            f"{report.target_type} #{report.target_id}.</p><p>Report ID: {report.id}</p>",
        )
    except Exception:
        logger.exception("Failed to notify admins about report %s", report.id)


def create_report(data, reporter_id, evidence_url=None):
    reporter = db.session.get(User, int(reporter_id))
    if not reporter:
        return jsonify({"error": "Unauthorized."}), 401

    target_type = str(data.get("target_type", "")).strip().lower()
    reason = str(data.get("reason", "")).strip().lower()
    try:
        target_id = int(data.get("target_id"))
    except (TypeError, ValueError):
        target_id = None

    errors = []
    if target_type not in REPORT_TARGET_TYPES:
        errors.append("target_type must be user, employer, or community.")
    if reason not in REPORT_REASONS:
        errors.append("reason is invalid.")
    if not target_id or (target_type in REPORT_TARGET_TYPES and not _target_exists(target_type, target_id)):
        errors.append("Target not found.")
    if errors:
        return _errors(errors)

    since = utc_now() - timedelta(hours=24)
    if Report.query.filter(Report.reporter_id == reporter.id, Report.created_at >= since).count() >= MAX_REPORTS_PER_24_HOURS:
        return jsonify({"error": "Report submission limit reached. Try again later."}), 429

    duplicate = Report.query.filter_by(
        reporter_id=reporter.id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        status="open",
    ).first()
    if duplicate:
        return jsonify({"error": "You already have an open report for this target and reason."}), 409

    description = str(data.get("description") or "").strip() or None
    report = Report(
        reporter_id=reporter.id,
        reporter_role=reporter.role,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        description=description,
        evidence_url=evidence_url,
    )
    db.session.add(report)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Failed to create report")
        return jsonify({"error": "Failed to submit report."}), 500
    _notify_admins(report)
    return jsonify({"message": "Report submitted.", "report": report.to_dict()}), 201


def _admin_report_dict(report):
    data = report.to_dict(include_reporter_id=True)
    if report.reporter:
        data["reporter"] = {
            "id": report.reporter.id,
            "full_name": report.reporter.full_name,
            "email": report.reporter.email,
            "role": report.reporter.role,
        }
    return data


def get_reports(args):
    query = Report.query
    for field, allowed in (("status", REPORT_STATUSES), ("target_type", REPORT_TARGET_TYPES), ("reason", REPORT_REASONS)):
        value = args.get(field)
        if value:
            if value not in allowed:
                return _errors([f"{field} is invalid."])
            query = query.filter(getattr(Report, field) == value)
    try:
        page = max(1, int(args.get("page", 1)))
        per_page = min(100, max(1, int(args.get("per_page", 20))))
    except (TypeError, ValueError):
        return _errors(["page and per_page must be integers."])
    result = query.order_by(Report.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "reports": [_admin_report_dict(r) for r in result.items],
        "pagination": {"page": page, "per_page": per_page, "total": result.total, "pages": result.pages},
    }), 200


def get_report(report_id):
    report = db.session.get(Report, report_id)
    if not report:
        return jsonify({"error": "Report not found."}), 404
    return jsonify({"report": _admin_report_dict(report)}), 200


def get_my_reports(reporter_id, args):
    try:
        page = max(1, int(args.get("page", 1)))
        per_page = min(100, max(1, int(args.get("per_page", 20))))
    except (TypeError, ValueError):
        return _errors(["page and per_page must be integers."])
    result = Report.query.filter_by(reporter_id=int(reporter_id)).order_by(Report.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "reports": [r.to_dict() for r in result.items],
        "pagination": {"page": page, "per_page": per_page, "total": result.total, "pages": result.pages},
    }), 200


def update_report(report_id, data, admin_id):
    report = db.session.get(Report, report_id)
    if not report:
        return jsonify({"error": "Report not found."}), 404
    status = data.get("status")
    if status is not None and status not in REPORT_STATUSES:
        return _errors(["status is invalid."])
    if status is None and "resolution_notes" not in data:
        return _errors(["status or resolution_notes is required."])
    if status is not None:
        report.status = status
        if status in ("resolved", "dismissed"):
            report.resolved_by = int(admin_id)
            report.resolved_at = utc_now()
        else:
            report.resolved_by = None
            report.resolved_at = None
    if "resolution_notes" in data:
        report.resolution_notes = str(data.get("resolution_notes") or "").strip() or None
    try:
        db.session.commit()
        return jsonify({"message": "Report updated.", "report": _admin_report_dict(report)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to update report."}), 500
