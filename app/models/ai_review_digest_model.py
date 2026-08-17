from app.extensions import db
from app.utils import utc_now


class AiReviewDigest(db.Model):
    """Cached AI review sentiment digest for a community (pricing-style event cache)."""

    __tablename__ = "ai_review_digests"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    community_id = db.Column(
        db.Integer, db.ForeignKey("communities.id"), nullable=False, unique=True
    )
    praised_json = db.Column(db.Text, nullable=False, default="[]")
    flagged_json = db.Column(db.Text, nullable=False, default="[]")
    review_count = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    community = db.relationship("Community")

    def to_dict(self):
        import json

        try:
            praised = json.loads(self.praised_json or "[]")
        except json.JSONDecodeError:
            praised = []
        try:
            flagged = json.loads(self.flagged_json or "[]")
        except json.JSONDecodeError:
            flagged = []
        return {
            "community_id": self.community_id,
            "praised": praised if isinstance(praised, list) else [],
            "flagged": flagged if isinstance(flagged, list) else [],
            "review_count": self.review_count,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "available": True,
        }
