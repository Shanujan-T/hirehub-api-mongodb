"""Add description column to open_calls for recruiting copy."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "open_calls" not in inspector.get_table_names():
            print("Skip: open_calls table missing.")
            return

        columns = {col["name"] for col in inspector.get_columns("open_calls")}
        if "description" in columns:
            print("Skip: open_calls.description already exists.")
            return

        db.session.execute(text("ALTER TABLE open_calls ADD COLUMN description TEXT NULL"))
        db.session.commit()
        print("Migration complete: open_calls.description added.")


if __name__ == "__main__":
    run_migration()
