from app.extensions import db
from app.utils import utc_now


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contract_id = db.Column(db.Integer, db.ForeignKey("contracts.id"), nullable=False, unique=True)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    commission_amount = db.Column(db.Numeric(10, 2), nullable=False)
    commission_recipient = db.Column(
        db.Enum("admin", "community_pool", "platform", name="commission_recipient"),
        nullable=False,
        default="admin",
    )
    member_payout = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(
        db.Enum("pending", "released", name="payment_status"),
        nullable=False,
        default="pending",
    )
    released_at = db.Column(db.DateTime, nullable=True)

    contract = db.relationship("Contract", back_populates="payment")

    def to_dict(self):
        return {
            "id": self.id,
            "contract_id": self.contract_id,
            "total_amount": float(self.total_amount) if self.total_amount else 0,
            "commission_amount": float(self.commission_amount) if self.commission_amount else 0,
            "commission_recipient": self.commission_recipient,
            "member_payout": float(self.member_payout) if self.member_payout else 0,
            "status": self.status,
            "released_at": self.released_at.isoformat() if self.released_at else None,
        }
