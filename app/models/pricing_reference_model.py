import json

from app.extensions import db


class PricingReference(db.Model):
    __tablename__ = "pricing_references"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category = db.Column(db.String(255), nullable=False)
    scope = db.Column(db.String(255), nullable=False)
    unit = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    base_price = db.Column(db.Numeric(10, 2), nullable=False)
    # JSON object keyed by canonical district name, imported from the pricing CSV.
    district_prices = db.Column(db.Text, nullable=True)

    def get_district_prices(self):
        try:
            data = json.loads(self.district_prices or "{}")
        except (TypeError, json.JSONDecodeError):
            data = {}
        return data if isinstance(data, dict) else {}

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "scope": self.scope,
            "unit": self.unit,
            "quantity": self.quantity,
            "basePrice": float(self.base_price) if self.base_price else 0.0,
            "districtPrices": self.get_district_prices(),
        }
