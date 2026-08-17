"""Add soft-delete columns to messages."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def _column_exists(inspector, table_name, column_name):
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "messages" not in inspector.get_table_names():
            print("Skip: messages table missing.")
            return

        columns = [
            ("deleted_for_everyone", "TINYINT(1) NOT NULL DEFAULT 0"),
            ("deleted_for_sender", "TINYINT(1) NOT NULL DEFAULT 0"),
            ("deleted_for_receiver", "TINYINT(1) NOT NULL DEFAULT 0"),
            ("deleted_at", "DATETIME NULL"),
        ]
        for name, ddl in columns:
            if not _column_exists(inspector, "messages", name):
                db.session.execute(text(f"ALTER TABLE messages ADD COLUMN {name} {ddl}"))

        db.session.commit()
        print("Migration complete: message soft-delete columns added.")
