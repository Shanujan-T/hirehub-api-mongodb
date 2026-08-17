"""Extend categories.baseline_unit with per_word / per_hour; set Content Writing to per_word."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "categories" not in inspector.get_table_names():
            print("Skip: categories table missing.")
            return

        columns = {col["name"] for col in inspector.get_columns("categories")}
        if "baseline_unit" not in columns:
            print("Skip: categories.baseline_unit missing (run 018 first).")
            return

        dialect = db.engine.dialect.name
        if dialect == "mysql":
            db.session.execute(
                text(
                    "ALTER TABLE categories MODIFY COLUMN baseline_unit "
                    "ENUM('per_job','per_sqft','per_word','per_hour') NULL"
                )
            )
            print("Extended categories.baseline_unit ENUM with per_word, per_hour")
        else:
            # SQLite / others store as VARCHAR — no enum alter needed.
            print("Skip ENUM alter (non-MySQL dialect).")

        # Content Writing: baseline is LKR per 100 words.
        result = db.session.execute(
            text(
                "UPDATE categories SET baseline_unit = 'per_word' "
                "WHERE name = 'Content Writing' AND (baseline_unit IS NULL OR baseline_unit = 'per_job')"
            )
        )
        print(f"Updated Content Writing baseline_unit to per_word (rows={result.rowcount})")

        db.session.commit()
        print("Migration complete: 022_category_pricing_units.")


if __name__ == "__main__":
    run_migration()
