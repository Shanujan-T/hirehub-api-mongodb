"""Add category_pricing.is_seeded_estimate and seed district pricing rows."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "category_pricing" not in inspector.get_table_names():
            print("Skip: category_pricing table missing.")
            return

        columns = {col["name"] for col in inspector.get_columns("category_pricing")}
        dialect = db.engine.dialect.name

        if "is_seeded_estimate" not in columns:
            if dialect == "mysql":
                db.session.execute(
                    text(
                        "ALTER TABLE category_pricing ADD COLUMN is_seeded_estimate "
                        "TINYINT(1) NOT NULL DEFAULT 0"
                    )
                )
            else:
                db.session.execute(
                    text(
                        "ALTER TABLE category_pricing ADD COLUMN is_seeded_estimate "
                        "BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
            print("Added category_pricing.is_seeded_estimate")
        else:
            print("Skip: category_pricing.is_seeded_estimate already exists.")

        db.session.commit()

        from app.utils.pricing_utils import seed_district_pricing

        result = seed_district_pricing()
        print(f"seed_district_pricing: {result}")
        print("Migration complete: 023_district_pricing_seed.")


if __name__ == "__main__":
    run_migration()
