from flask import jsonify

from app.models.community_model import Community
from app.models.contract_model import Contract
from app.models.job_model import Job


def get_public_stats():
    return jsonify(
        {
            "stats": {
                "communities": Community.query.count(),
                "jobs": Job.query.count(),
                "contracts_completed": Contract.query.filter_by(status="completed").count(),
            }
        }
    ), 200
