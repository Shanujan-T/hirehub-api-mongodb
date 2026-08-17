"""Add image_url column to communities."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def _column_exists(inspector, table_name, column_name):
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if _column_exists(inspector, "communities", "image_url"):
            print("Migration skipped: communities.image_url already exists.")
            return

        db.session.execute(
            text("ALTER TABLE communities ADD COLUMN image_url VARCHAR(512) NULL")
        )
        db.session.commit()
        print("Migration complete: communities.image_url added.")


if __name__ == "__main__":
    run_migration()
