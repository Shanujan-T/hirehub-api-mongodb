"""Add optional private postal address fields on users."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def _column_exists(inspector, table_name, column_name):
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        columns = [
            ("address_line1", "VARCHAR(255) NULL"),
            ("address_line2", "VARCHAR(255) NULL"),
            ("address_city", "VARCHAR(128) NULL"),
            ("address_region", "VARCHAR(128) NULL"),
            ("address_postal_code", "VARCHAR(32) NULL"),
        ]
        for name, ddl in columns:
            if not _column_exists(inspector, "users", name):
                db.session.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))

        db.session.commit()
        print("Migration complete: user private address fields added.")


if __name__ == "__main__":
    run_migration()
