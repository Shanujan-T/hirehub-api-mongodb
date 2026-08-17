"""Store the CSV's per-district service prices on each pricing reference row."""

import csv
import json
from pathlib import Path

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


DISTRICTS = (
    "Colombo", "Gampaha", "Kalutara", "Kandy", "Galle",
    "Matara", "Jaffna", "Kurunegala", "Anuradhapura", "Badulla",
)


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "pricing_references" not in inspector.get_table_names():
            print("Skip: pricing_references table does not exist yet.")
            return

        columns = {column["name"] for column in inspector.get_columns("pricing_references")}
        if "district_prices" not in columns:
            db.session.execute(text("ALTER TABLE pricing_references ADD COLUMN district_prices TEXT NULL"))
            db.session.commit()
            print("Added pricing_references.district_prices")

        csv_path = Path(__file__).resolve().parent.parent / "seeders" / "data" / "Sri_Lanka_Service_Pricing_Dataset.csv"
        with csv_path.open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))

        updated = 0
        for row in rows:
            category = (row.get("Category") or "").strip()
            scope = (row.get("Scope") or "").strip()
            unit = (row.get("Unit") or "").strip()
            quantity = int((row.get("Quantity") or "0").strip() or 0)
            prices = {
                district: float(row[district])
                for district in DISTRICTS
                if (row.get(district) or "").strip()
            }
            result = db.session.execute(
                text(
                    """UPDATE pricing_references SET district_prices = :district_prices
                    WHERE category = :category AND scope = :scope AND unit = :unit AND quantity = :quantity"""
                ),
                {
                    "district_prices": json.dumps(prices), "category": category,
                    "scope": scope, "unit": unit, "quantity": quantity,
                },
            )
            updated += result.rowcount or 0
        db.session.commit()
        print(f"Migration complete: pricing reference district prices updated={updated}.")


if __name__ == "__main__":
    run_migration()
