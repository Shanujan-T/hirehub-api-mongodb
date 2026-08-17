"""Backfill example scope schemas for Landscaping and Web Development (retrofit)."""

import json

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db

_EXAMPLES = {
    "Landscaping": [
        {
            "key": "area_sqft",
            "label": "Area (sq ft)",
            "type": "number",
            "unit": "sq ft",
            "required": True,
        }
    ],
    "Web Development": [
        {"key": "pages", "label": "Number of pages", "type": "number", "required": True},
        {
            "key": "features",
            "label": "Features needed",
            "type": "multiselect",
            "required": True,
            "options": [
                "Portfolio",
                "Blog/CMS",
                "E-commerce",
                "User Auth",
                "Payment Integration",
                "Custom Admin Dashboard",
            ],
        },
    ],
}


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "categories" not in inspector.get_table_names():
            print("Skip: categories table missing.")
            return
        columns = {col["name"] for col in inspector.get_columns("categories")}
        if "scope_schema" not in columns:
            print("Skip: categories.scope_schema missing (run 014 first).")
            return

        updated = 0
        for name, schema in _EXAMPLES.items():
            row = db.session.execute(
                text(
                    "SELECT id, scope_schema FROM categories WHERE name = :name LIMIT 1"
                ),
                {"name": name},
            ).first()
            if not row:
                print(f"Skip: category '{name}' not found.")
                continue
            existing = row[1]
            if existing and str(existing).strip() not in ("", "null", "[]"):
                print(f"Skip: '{name}' already has scope_schema.")
                continue
            db.session.execute(
                text("UPDATE categories SET scope_schema = :schema WHERE id = :id"),
                {"schema": json.dumps(schema, ensure_ascii=False), "id": row[0]},
            )
            updated += 1
            print(f"Set scope_schema for '{name}'.")

        db.session.commit()
        print(f"Migration complete: 016_seed_example_scope_schemas (updated={updated}).")


if __name__ == "__main__":
    run_migration()
