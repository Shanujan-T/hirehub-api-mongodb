"""Add pricing_references table and seed reference values from Sri Lanka service pricing dataset CSV."""

import csv
from pathlib import Path
from sqlalchemy import inspect, text
from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        table_exists = "pricing_references" in inspector.get_table_names()

        # 1. Create table if not exists
        if not table_exists:
            dialect = db.engine.dialect.name
            if dialect == "mysql":
                db.session.execute(
                    text(
                        """
                        CREATE TABLE pricing_references (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            category VARCHAR(255) NOT NULL,
                            scope VARCHAR(255) NOT NULL,
                            unit VARCHAR(255) NOT NULL,
                            quantity INT NOT NULL,
                            base_price DECIMAL(10, 2) NOT NULL
                        )
                        """
                    )
                )
            else:
                db.session.execute(
                    text(
                        """
                        CREATE TABLE pricing_references (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            category VARCHAR(255) NOT NULL,
                            scope VARCHAR(255) NOT NULL,
                            unit VARCHAR(255) NOT NULL,
                            quantity INTEGER NOT NULL,
                            base_price NUMERIC(10, 2) NOT NULL
                        )
                        """
                    )
                )
            db.session.commit()
            print("Created table: pricing_references")
        else:
            print("Skip: table pricing_references already exists.")

        # 2. Check if table is empty and seed if necessary
        count_res = db.session.execute(text("SELECT COUNT(*) FROM pricing_references")).first()
        count = count_res[0] if count_res else 0

        if count == 0:
            csv_path = (
                Path(__file__).resolve().parent.parent
                / "seeders"
                / "data"
                / "Sri_Lanka_Service_Pricing_Dataset.csv"
            )
            if not csv_path.exists():
                print(f"Error: Seed file not found at {csv_path}")
                return

            print(f"Seeding pricing_references from {csv_path}...")
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = []
                for row in reader:
                    category = row.get("Category", "").strip()
                    scope = row.get("Scope", "").strip()
                    unit = row.get("Unit", "").strip()
                    qty_str = row.get("Quantity", "0").strip()
                    price_str = row.get("BasePrice", "0").strip()

                    if not category or not scope:
                        continue

                    try:
                        quantity = int(qty_str)
                    except ValueError:
                        quantity = 0

                    try:
                        base_price = float(price_str)
                    except ValueError:
                        base_price = 0.0

                    rows.append({
                        "category": category,
                        "scope": scope,
                        "unit": unit,
                        "quantity": quantity,
                        "base_price": base_price,
                    })

                if rows:
                    db.session.execute(
                        text(
                            """
                            INSERT INTO pricing_references (category, scope, unit, quantity, base_price)
                            VALUES (:category, :scope, :unit, :quantity, :base_price)
                            """
                        ),
                        rows,
                    )
                    db.session.commit()
                    print(f"Seeded {len(rows)} rows into pricing_references.")
        else:
            print(f"Skip: pricing_references table already has {count} rows.")

        print("Migration complete: 027_pricing_reference.")


if __name__ == "__main__":
    run_migration()
