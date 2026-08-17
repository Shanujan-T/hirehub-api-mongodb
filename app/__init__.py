import logging
import os
import re
from pathlib import Path
from collections import defaultdict

from flask import Flask, abort, jsonify, send_from_directory
from flask_cors import CORS
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.config import Config
from app.extensions import db, jwt, socketio
from app.models.user_model import User
from app.routes import register_blueprints

_GROUP_ORDER = [
    "auth",
    "ai",
    "users",
    "skills",
    "user_skills",
    "communities",
    "community_members",
    "open_calls",
    "categories",
    "category_pricing",
    "jobs",
    "community_applications",
    "contracts",
    "contract_applications",
    "payments",
    "reviews",
    "reports",
    "notifications",
]

_METHOD_ORDER = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 4}
_ALLOWED_METHODS = set(_METHOD_ORDER)
_EXCLUDED_ENDPOINTS = {"api_home", "static"}

_PRICING_PATH_MARKERS = ("/pricing-suggestion", "/seed-pricing", "/recalc-pricing")

_BLUEPRINT_DEFAULT_GROUP = {
    "auth": "auth",
    "ai": "ai",
    "users": "users",
    "skills": "skills",
    "user_skills": "user_skills",
    "communities": "communities",
    "community_members": "community_members",
    "open_calls": "open_calls",
    "jobs": "jobs",
    "community_applications": "community_applications",
    "contracts": "contracts",
    "contract_applications": "contract_applications",
    "payments": "payments",
    "reviews": "reviews",
    "reports": "reports",
}

_DESCRIPTIONS = {
    ("POST", "/api/auth/register"): "Register a user (posts jobs) or employer (does community work) account",
    ("POST", "/api/auth/login"): "Log in and receive a JWT access token",
    ("GET", "/api/auth/me"): "Get current authenticated user profile",
    ("GET", "/api/users"): "List users",
    ("GET", "/api/users/:id"): "Get a single user",
    ("PUT", "/api/users/:id"): "Update a user profile",
    ("POST", "/api/users/:id/avatar"): "Upload a user avatar image",
    ("DELETE", "/api/users/:id/avatar"): "Remove a user avatar image",
    ("POST", "/api/users/me/nic-document"): "Deprecated — NIC upload removed; use phone/email OTP",
    ("POST", "/api/users/me/identity-verification"): "Deprecated — NIC submission removed; use phone/email OTP",
    ("POST", "/api/users/me/identity-verification/phone/send"): "Send SMS OTP for phone account verification",
    ("POST", "/api/users/me/identity-verification/phone/confirm"): "Confirm phone OTP for account verification",
    ("POST", "/api/users/me/identity-verification/email/send"): "Send email OTP for account verification",
    ("POST", "/api/users/me/identity-verification/email/confirm"): "Confirm email OTP for account verification",
    ("PUT", "/api/users/:id/identity-verification/review"): "Deprecated — legacy NIC admin review removed",
    ("DELETE", "/api/users/:id"): "Delete a user",
    ("GET", "/api/skills"): "List all skills",
    ("POST", "/api/skills"): "Create a new skill",
    ("GET", "/api/skills/:id"): "Get a single skill",
    ("PUT", "/api/skills/:id"): "Update a skill",
    ("DELETE", "/api/skills/:id"): "Delete a skill",
    ("GET", "/api/user-skills"): "List user skills",
    ("POST", "/api/user-skills"): "Create a user skill link",
    ("GET", "/api/user-skills/:id"): "Get a user skill",
    ("PUT", "/api/user-skills/:id"): "Update a user skill",
    ("DELETE", "/api/user-skills/:id"): "Delete a user skill",
    ("GET", "/api/communities"): "List communities",
    ("POST", "/api/communities"): "Create a community",
    ("GET", "/api/communities/:id"): "Get a single community",
    ("PUT", "/api/communities/:id"): "Update a community",
    ("PATCH", "/api/communities/:id/verify"): "Verify or reject a community submission (admin)",
    ("PUT", "/api/communities/:id/review"): "Review a community submission (admin, legacy)",
    ("POST", "/api/communities/:id/image"): "Upload a community image",
    ("DELETE", "/api/communities/:id"): "Delete a community",
    ("GET", "/api/community-members/my"): "List my community memberships",
    ("POST", "/api/community-members/join/:id"): "Request to join a community",
    ("GET", "/api/community-members/community/:id"): "List members of a community",
    ("POST", "/api/community-members/:id/approve"): "Approve a membership request",
    ("POST", "/api/community-members/:id/reject"): "Reject a membership request",
    ("DELETE", "/api/community-members/:id"): "Remove a community member",
    ("GET", "/api/open-calls"): "List open calls",
    ("POST", "/api/open-calls"): "Create an open call",
    ("GET", "/api/open-calls/:id"): "Get a single open call",
    ("PUT", "/api/open-calls/:id"): "Update an open call",
    ("DELETE", "/api/open-calls/:id"): "Delete an open call",
    ("GET", "/api/categories"): "List approved job categories (admin: ?status=pending|all)",
    ("POST", "/api/categories"): "Create an approved category (admin)",
    ("POST", "/api/categories/request"): "Request a new category (pending admin review)",
    ("GET", "/api/categories/:id"): "Get a single category",
    ("PUT", "/api/categories/:id"): "Update a category / scope schema (admin)",
    ("DELETE", "/api/categories/:id"): "Delete a category",
    ("POST", "/api/categories/:id/approve"): "Approve a pending category request (admin)",
    ("POST", "/api/categories/:id/reject"): "Reject a pending category request (admin)",
    ("GET", "/api/categories/:id/pricing-suggestion"): "Get suggested price for category + location",
    ("POST", "/api/categories/:id/seed-pricing"): "Seed pricing data for a category",
    ("POST", "/api/categories/:id/seed-district-pricing"): "Seed tiered district estimate rows from baseline_price",
    ("POST", "/api/categories/seed-district-pricing"): "Seed district estimates for all categories with a baseline",
    ("POST", "/api/categories/:id/recalc-pricing"): "Recalculate category pricing by location",
    ("GET", "/api/jobs"): "List jobs for current user",
    ("POST", "/api/jobs"): "Create a new job posting",
    ("GET", "/api/jobs/:id"): "Get a single job",
    ("PUT", "/api/jobs/:id"): "Update a job posting",
    ("DELETE", "/api/jobs/:id"): "Delete a job posting",
    ("GET", "/api/jobs/:id/applications"): "List applications for a job",
    ("POST", "/api/ai/concierge"): "AI Community Concierge Q&A (user-scoped)",
    ("GET", "/api/ai/concierge"): "AI Community Concierge availability status",
    ("GET", "/api/jobs/:id/recommended-communities"): "Ranked community matches for a job (poster)",
    ("POST", "/api/jobs/:id/suggest-bid"): "AI bid suggestion for a community admin",
    ("POST", "/api/jobs/:id/invite"): "Invite a community to a job (job poster)",
    ("POST", "/api/jobs/generate-description"): "AI job title/description/category generator",
    ("GET", "/api/communities/:id/recommended-jobs"): "Ranked job matches for a community (admin)",
    ("POST", "/api/communities/:id/join-requests/:id/fit-analysis"): "AI skill-fit analysis for a pending join request",
    ("GET", "/api/community-applications/my"): "List my community job applications",
    ("POST", "/api/community-applications/apply"): "Apply community to a job",
    ("GET", "/api/community-applications/job/:id"): "List applications for a job",
    ("POST", "/api/community-applications/:id/approve"): "Approve a community application",
    ("POST", "/api/community-applications/:id/reject"): "Reject a community application",
    ("GET", "/api/contracts"): "List contracts for current user",
    ("GET", "/api/contracts/needs-attention"): "List at-risk contracts needing attention",
    ("GET", "/api/contracts/:id"): "Get a single contract",
    ("POST", "/api/contracts/:id/open-internally"): "Open contract for internal hiring",
    ("POST", "/api/contracts/:id/select-member"): "Select a member for contract",
    ("POST", "/api/contracts/:id/submit-deliverable"): "Submit contract deliverable",
    ("POST", "/api/contracts/:id/admin-approve-deliverable"): "Admin approve submitted deliverable",
    ("POST", "/api/contracts/:id/poster-approve-deliverable"): "Job poster approve submitted deliverable",
    ("POST", "/api/contracts/:id/client-approve-deliverable"): "Legacy alias for poster-approve-deliverable",
    ("POST", "/api/contracts/:id/ai-review-deliverable"): "AI assistive pre-check for a submitted deliverable",
    ("GET", "/api/contracts/:id/messages"): "List contract conversation messages",
    ("POST", "/api/contracts/:id/messages"): "Send a contract conversation message",
    ("POST", "/api/contracts/:id/messages/suggest-reply"): "AI suggested reply draft for contract chat",
    ("POST", "/api/user-skills/:id/work-samples"): "Add a work sample for a user skill",
    ("GET", "/api/user-skills/:id/work-samples"): "List work samples for a user skill",
    ("POST", "/api/work-samples/:id/verify"): "AI-verify a work sample (text or best-effort image)",
    ("GET", "/api/contract-applications/my"): "List my contract applications",
    ("POST", "/api/contract-applications/apply"): "Apply to an open contract",
    ("GET", "/api/contract-applications/contract/:id"): "List applications for a contract",
    ("GET", "/api/payments/my-earnings"): "Get my earnings summary",
    ("GET", "/api/payments"): "List payments for current user",
    ("GET", "/api/reviews"): "List reviews",
    ("POST", "/api/reviews"): "Create a contract review",
    ("DELETE", "/api/messages/:id/delete-for-me"): "Delete a message for the current user only",
    ("DELETE", "/api/messages/:id/delete-for-everyone"): "Delete a message for all participants",
    ("GET", "/api/notifications"): "List notifications for current user",
    ("GET", "/api/notifications/unread-count"): "Unread notification count",
    ("PATCH", "/api/notifications/:id/read"): "Mark one notification read",
    ("PATCH", "/api/notifications/read-all"): "Mark all notifications read",
    ("GET", "/api/reports"): "List moderation reports",
    ("POST", "/api/reports"): "Submit a moderation report",
    ("GET", "/api/reports/mine"): "List reports filed by the current user",
    ("GET", "/api/reports/:id"): "Get a single moderation report",
    ("GET", "/api/reports/:id/ai-summary"): "AI dispute summary for platform admins",
    ("PATCH", "/api/reports/:id"): "Update a report status",
    ("GET", "/api/communities/:id/review-digest"): "Cached AI review sentiment digest",
    ("POST", "/api/open-calls/generate-description"): "AI open-call recruiting description draft",
}


def _normalize_path(rule_path):
    return re.sub(r"<[^>]+>", ":id", rule_path)


def _group_for_rule(blueprint_name, path):
    if blueprint_name == "categories" and any(marker in path for marker in _PRICING_PATH_MARKERS):
        return "category_pricing"
    return _BLUEPRINT_DEFAULT_GROUP.get(blueprint_name, blueprint_name)


def _endpoint_description(method, path, endpoint):
    key = (method, path)
    if key in _DESCRIPTIONS:
        return _DESCRIPTIONS[key]
    action = endpoint.split(".")[-1].replace("_", " ")
    return action[:1].upper() + action[1:]


def _build_endpoint_index(app):
    grouped = defaultdict(list)
    seen = set()

    for rule in app.url_map.iter_rules():
        if rule.endpoint in _EXCLUDED_ENDPOINTS:
            continue

        blueprint_name = rule.endpoint.split(".")[0]
        path = _normalize_path(rule.rule)

        for method in sorted(rule.methods & _ALLOWED_METHODS, key=lambda m: _METHOD_ORDER[m]):
            key = (method, path)
            if key in seen:
                continue
            seen.add(key)

            group = _group_for_rule(blueprint_name, path)
            grouped[group].append(
                {
                    "method": method,
                    "path": path,
                    "description": _endpoint_description(method, path, rule.endpoint),
                }
            )

    for group in grouped:
        grouped[group].sort(key=lambda entry: (_METHOD_ORDER[entry["method"]], entry["path"]))

    return {
        "api": "HireHub API",
        "version": "1.0",
        "endpoints": {group: grouped[group] for group in _GROUP_ORDER if group in grouped},
    }


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)
    db.init_app(app)
    jwt.init_app(app)
    socketio.init_app(app)

    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data["sub"]
        return User.query.get(int(identity))

    def _is_schema_operational_error(exc):
        """PyMySQL reports unknown-column / missing-table as OperationalError (not ProgrammingError)."""
        orig = getattr(exc, "orig", None)
        errno = getattr(orig, "args", [None])[0] if orig is not None else None
        # 1054 unknown column, 1146 table doesn't exist, 1051 unknown table
        return errno in (1051, 1054, 1146)

    def _schema_error_response(e):
        logging.getLogger(__name__).exception(
            "Database schema error type=%s message=%s", type(e).__name__, e
        )
        details = str(e) if app.config.get("DEBUG") else None
        return (
            jsonify(
                {
                    "error": "Database schema is out of date. Run migrations/run_all.py on the API.",
                    "details": details,
                }
            ),
            503,
        )

    @app.errorhandler(OperationalError)
    def handle_db_connection_error(e):
        if _is_schema_operational_error(e):
            return _schema_error_response(e)
        logging.getLogger(__name__).exception(
            "Database connection error type=%s message=%s", type(e).__name__, e
        )
        details = str(e) if app.config.get("DEBUG") else None
        return jsonify({"error": "Database connection error.", "details": details}), 503

    @app.errorhandler(ProgrammingError)
    def handle_db_schema_error(e):
        return _schema_error_response(e)

    with app.app_context():
        from app.models import (  # noqa: F401
            ai_match_blurb_model,
            ai_review_digest_model,
            category_model,
            category_pricing_model,
            community_application_model,
            community_member_model,
            community_model,
            contract_application_model,
            contract_model,
            conversation_model,
            job_model,
            message_model,
            notification_model,
            open_call_model,
            open_call_skill_model,
            payment_model,
            pricing_reference_model,
            report_model,
            review_model,
            skill_model,
            user_model,
            user_skill_model,
            verification_otp_model,
            work_sample_model,
        )

        try:
            db.create_all()
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Database tables not initialized at startup: %s", exc
            )

    register_blueprints(app)

    from . import socket_events  # noqa: F401
    from app.scheduler import start_scheduler_once

    start_scheduler_once(app)

    @app.route("/")
    def api_home():
        return _build_endpoint_index(app)

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        local_uploads_enabled = (
            app.debug
            and os.getenv("LOCAL_UPLOADS_ENABLED", "0") == "1"
            and not os.getenv("RAILWAY_ENVIRONMENT")
        )
        if not local_uploads_enabled:
            abort(404)
        return send_from_directory(Path(app.instance_path) / "uploads", filename)

    return app
