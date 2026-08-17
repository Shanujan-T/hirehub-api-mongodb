from app.extensions import db
from app.utils import utc_now


class ContractApplication(db.Model):
    __tablename__ = "contract_applications"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contract_id = db.Column(db.Integer, db.ForeignKey("contracts.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    note = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.Enum("applied", "selected", "rejected", name="contract_application_status"),
        nullable=False,
        default="applied",
    )
    origin = db.Column(
        db.Enum("applied", "direct_assign", name="contract_application_origin"),
        nullable=False,
        default="applied",
    )
    payout_percent = db.Column(db.Numeric(5, 2), nullable=True)
    payout_amount = db.Column(db.Numeric(10, 2), nullable=True)
    applied_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    __table_args__ = (db.UniqueConstraint("contract_id", "member_id"),)

    contract = db.relationship("Contract", back_populates="contract_applications")
    member = db.relationship("User", back_populates="contract_applications")

    def to_dict(self, include_member=False):
        data = {
            "id": self.id,
            "contract_id": self.contract_id,
            "member_id": self.member_id,
            "note": self.note,
            "status": self.status,
            "origin": self.origin,
            "payout_percent": float(self.payout_percent) if self.payout_percent is not None else None,
            "payout_amount": float(self.payout_amount) if self.payout_amount is not None else None,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
        }
        if include_member and self.member:
            data["member"] = self.member.to_dict(include_stats=True, include_skills=True)
        return data
