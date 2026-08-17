from flask import Blueprint

from app.controllers import stats_controller

stats_bp = Blueprint("stats", __name__, url_prefix="/api/stats")


@stats_bp.route("", methods=["GET"])
def public_stats():
    return stats_controller.get_public_stats()
