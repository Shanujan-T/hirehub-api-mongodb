from app.extensions import db
from app.utils import utc_now


REPORT_TARGET_TYPES = ("user", "employer", "community")
REPORT_REASONS = (
    "fraud_or_scam",
    "no_show_or_abandoned_job",
    "harassment_or_abuse",
    "fake_profile",
    "unsafe_behavior",
    "payment_dispute",
    "inappropriate_content",
    "other",
)
REPORT_STATUSES = ("open", "under_review", "resolved", "dismissed")


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reporter_role = db.Column(db.String(32), nullable=False)
    target_type = db.Column(db.Enum(*REPORT_TARGET_TYPES, name="report_target_type"), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Enum(*REPORT_REASONS, name="report_reason"), nullable=False)
    description = db.Column(db.Text, nullable=True)
    evidence_url = db.Column(db.String(512), nullable=True)
    status = db.Column(
        db.Enum(*REPORT_STATUSES, name="report_status"), nullable=False, default="open"
    )
    resolution_notes = db.Column(db.Text, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    reporter = db.relationship("User", foreign_keys=[reporter_id])
    resolver = db.relationship("User", foreign_keys=[resolved_by])

    __table_args__ = (
        db.Index("ix_reports_filters", "status", "target_type", "reason"),
        db.Index("ix_reports_reporter_created", "reporter_id", "created_at"),
    )

    def to_dict(self, include_reporter_id=False):
        data = {
            "id": self.id,
            "reporter_role": self.reporter_role,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "reason": self.reason,
            "description": self.description,
            "evidence_url": self.evidence_url,
            "status": self.status,
            "resolution_notes": self.resolution_notes,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_reporter_id:
            data["reporter_id"] = self.reporter_id
        return data
