from app.extensions import db
from app.utils import utc_now


class WorkSample(db.Model):
    __tablename__ = "work_samples"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_skill_id = db.Column(
        db.Integer, db.ForeignKey("user_skills.id", ondelete="CASCADE"), nullable=False
    )
    sample_type = db.Column(
        db.Enum("text", "image", name="work_sample_type"),
        nullable=False,
    )
    content = db.Column(db.Text, nullable=False)
    ai_assessment = db.Column(db.Text, nullable=True)
    verification_status = db.Column(
        db.Enum("unreviewed", "plausible", "unclear", name="work_sample_verification"),
        nullable=False,
        default="unreviewed",
    )
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user_skill = db.relationship("UserSkill", back_populates="work_samples")

    def to_dict(self):
        return {
            "id": self.id,
            "user_skill_id": self.user_skill_id,
            "sample_type": self.sample_type,
            "content": self.content,
            "ai_assessment": self.ai_assessment,
            "verification_status": self.verification_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
