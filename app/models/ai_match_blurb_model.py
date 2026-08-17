from app.extensions import db
from app.utils import utc_now


class AiMatchBlurb(db.Model):
    """Cached one-sentence AI blurb for a job↔community match pair."""

    __tablename__ = "ai_match_blurbs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=False)
    blurb = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("job_id", "community_id", name="uq_ai_match_job_community"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "community_id": self.community_id,
            "blurb": self.blurb,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
