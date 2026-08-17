from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import ai_features_controller, report_controller
from app.middleware import roles_required
from app.utils.cloudinary_client import upload_image, validate_image_file

reports_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@reports_bp.route("", methods=["GET"])
@roles_required("admin")
def list_reports():
    return report_controller.get_reports(request.args)


@reports_bp.route("", methods=["POST"])
@jwt_required()
def create_report():
    evidence_url = None
    if request.content_type and "multipart/form-data" in request.content_type:
        data = request.form.to_dict()
        evidence = request.files.get("evidence") or request.files.get("file")
        if evidence:
            error = validate_image_file(evidence)
            if error:
                return jsonify({"errors": [error]}), 400
            try:
                evidence_url = upload_image(evidence, "hirehub/report-evidence")
            except ValueError as exc:
                return jsonify({"errors": [str(exc)]}), 400
            except Exception:
                return jsonify({"error": "Evidence upload failed."}), 500
    else:
        data = request.get_json(silent=True) or {}
    return report_controller.create_report(data, get_jwt_identity(), evidence_url)


@reports_bp.route("/mine", methods=["GET"])
@jwt_required()
def my_reports():
    return report_controller.get_my_reports(get_jwt_identity(), request.args)


@reports_bp.route("/<int:report_id>", methods=["GET"])
@roles_required("admin")
def get_report(report_id):
    return report_controller.get_report(report_id)


@reports_bp.route("/<int:report_id>/ai-summary", methods=["GET"])
@roles_required("admin")
def report_ai_summary(report_id):
    return ai_features_controller.summarize_dispute(report_id, int(get_jwt_identity()))


@reports_bp.route("/<int:report_id>", methods=["PATCH"])
@roles_required("admin")
def update_report(report_id):
    return report_controller.update_report(report_id, request.get_json(silent=True) or {}, get_jwt_identity())
