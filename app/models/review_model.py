from app.extensions import db
from app.utils import utc_now


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contract_id = db.Column(db.Integer, db.ForeignKey("contracts.id"), nullable=False, unique=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    contract = db.relationship("Contract", back_populates="reviews")
    reviewer = db.relationship(
        "User", back_populates="reviews_given", foreign_keys=[reviewer_id]
    )
    community = db.relationship("Community")
    member = db.relationship("User", foreign_keys=[member_id])

    def to_dict(self):
        return {
            "id": self.id,
            "contract_id": self.contract_id,
            "reviewer_id": self.reviewer_id,
            "community_id": self.community_id,
            "member_id": self.member_id,
            "rating": self.rating,
            "comment": self.comment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
