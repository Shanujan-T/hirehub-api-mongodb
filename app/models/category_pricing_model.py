from app.extensions import db
from app.utils import utc_now


class CategoryPricing(db.Model):
    __tablename__ = "category_pricing"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    average_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    sample_size = db.Column(db.Integer, nullable=False, default=0)
    is_seeded_estimate = db.Column(db.Boolean, nullable=False, default=False)
    last_updated = db.Column(db.DateTime, default=utc_now, nullable=False)

    __table_args__ = (db.UniqueConstraint("category_id", "location"),)

    category = db.relationship("Category", back_populates="pricing")

    def to_dict(self):
        return {
            "id": self.id,
            "category_id": self.category_id,
            "location": self.location,
            "average_price": float(self.average_price) if self.average_price else 0,
            "sample_size": self.sample_size,
            "is_seeded_estimate": bool(self.is_seeded_estimate),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }
