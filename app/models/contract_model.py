from app.extensions import db
from app.utils import utc_now


class Contract(db.Model):
    __tablename__ = "contracts"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False, unique=True)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=False)
    assigned_member_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    commission_percent = db.Column(db.Numeric(5, 2), nullable=False, default=3.0)
    commission_amount = db.Column(db.Numeric(10, 2), nullable=True)
    member_payout = db.Column(db.Numeric(10, 2), nullable=True)
    status = db.Column(
        db.Enum(
            "pending_assignment",
            "open_internally",
            "active",
            "submitted",
            "completed",
            "disputed",
            name="contract_status",
        ),
        nullable=False,
        default="pending_assignment",
    )
    deliverable_url = db.Column(db.String(512), nullable=True)
    risk_level = db.Column(
        db.Enum("none", "low", "high", name="contract_risk_level"),
        nullable=False,
        default="none",
    )
    risk_reason = db.Column(db.Text, nullable=True)
    risk_flags = db.Column(db.String(255), nullable=True)
    risk_checked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    job = db.relationship("Job", back_populates="contract")
    community = db.relationship("Community", back_populates="contracts")
    assigned_member = db.relationship(
        "User", back_populates="assigned_contracts", foreign_keys=[assigned_member_id]
    )
    contract_applications = db.relationship(
        "ContractApplication", back_populates="contract", lazy="dynamic"
    )
    payment = db.relationship("Payment", back_populates="contract", uselist=False)
    reviews = db.relationship("Review", back_populates="contract", lazy="dynamic")
    conversation = db.relationship(
        "Conversation", back_populates="contract", uselist=False
    )

    def to_dict(self, include_job=False, strip_poster=False, include_community=False):
        data = {
            "id": self.id,
            "job_id": self.job_id,
            "community_id": self.community_id,
            "assigned_member_id": self.assigned_member_id,
            "total_amount": float(self.total_amount) if self.total_amount else 0,
            "commission_percent": float(self.commission_percent) if self.commission_percent else 0,
            "commission_amount": float(self.commission_amount) if self.commission_amount else None,
            "member_payout": float(self.member_payout) if self.member_payout else None,
            "status": self.status,
            "deliverable_url": self.deliverable_url,
            "risk_level": self.risk_level or "none",
            "risk_reason": self.risk_reason,
            "risk_flags": (
                [f for f in (self.risk_flags or "").split(",") if f] if self.risk_flags else []
            ),
            "risk_checked_at": self.risk_checked_at.isoformat() if self.risk_checked_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_job and self.job:
            data["job"] = self.job.to_dict(strip_poster=strip_poster)
        if include_community and self.community:
            data["community"] = self.community.to_dict()
        if self.assigned_member:
            data["assigned_member"] = self.assigned_member.to_dict(include_stats=True)
        return data
