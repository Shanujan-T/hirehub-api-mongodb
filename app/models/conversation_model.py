from app.extensions import db
from app.utils import utc_now


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contract_id = db.Column(db.Integer, db.ForeignKey("contracts.id"), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    contract = db.relationship("Contract", back_populates="conversation")
    messages = db.relationship("Message", back_populates="conversation", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "contract_id": self.contract_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
