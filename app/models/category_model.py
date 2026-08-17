import json

from app.extensions import db
from app.utils import utc_now
from app.utils.scope_utils import parse_json_value, pricing_unit_from_schema


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    # JSON array of field defs (also exposed as scope_fields in API responses).
    scope_schema = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.Enum("pending", "approved", "rejected", name="category_status"),
        nullable=False,
        default="approved",
    )
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    request_description = db.Column(db.Text, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    baseline_price = db.Column(db.Numeric(12, 2), nullable=True)
    baseline_scope_key = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    pricing = db.relationship("CategoryPricing", back_populates="category", lazy="dynamic")
    jobs = db.relationship("Job", back_populates="category", lazy="dynamic")
    communities = db.relationship("Community", back_populates="category", lazy="dynamic")
    requested_by = db.relationship("User", foreign_keys=[requested_by_id])

    def get_scope_schema(self):
        data = parse_json_value(self.scope_schema)
        return data if isinstance(data, list) else None

    def set_scope_schema(self, value):
        if value is None:
            self.scope_schema = None
        else:
            self.scope_schema = json.dumps(value, ensure_ascii=False)

    def pricing_unit(self) -> str:
        """flat | scaled — derived from whether any numeric scope field affects price."""
        return pricing_unit_from_schema(self.get_scope_schema())

    def to_dict(self, include_requester=False):
        schema = self.get_scope_schema()
        data = {
            "id": self.id,
            "name": self.name,
            "scope_schema": schema,
            # Alias for the generic scope-fields API (same JSON column).
            "scope_fields": schema,
            "status": self.status,
            "requested_by_id": self.requested_by_id,
            "request_description": self.request_description,
            "rejection_reason": self.rejection_reason if self.status == "rejected" else None,
            "baseline_price": float(self.baseline_price) if self.baseline_price is not None else None,
            "baseline_scope_key": self.baseline_scope_key,
            "pricing_unit": self.pricing_unit(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_requester and self.requested_by:
            data["requested_by"] = {
                "id": self.requested_by.id,
                "full_name": self.requested_by.full_name,
                "email": self.requested_by.email,
            }
        return data
