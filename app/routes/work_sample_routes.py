from flask import Blueprint
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.controllers import work_sample_controller
from app.middleware import roles_required

work_samples_bp = Blueprint("work_samples", __name__, url_prefix="/api/work-samples")


@work_samples_bp.route("/<int:sample_id>/verify", methods=["POST"])
@roles_required("employer")
def verify_work_sample(sample_id):
    return work_sample_controller.verify_work_sample(sample_id, int(get_jwt_identity()))
