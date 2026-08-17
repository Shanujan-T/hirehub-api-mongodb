"""Collapse client role into user and rename jobs.client_id to posted_by_id."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def _column_exists(inspector, table_name, column_name):
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _role_enum_includes(inspector, value):
    cols = inspector.get_columns("users")
    role_col = next((c for c in cols if c["name"] == "role"), None)
    if not role_col:
        return False
    return value in str(role_col.get("type", ""))


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)

        if _role_enum_includes(inspector, "client"):
            db.session.execute(text("UPDATE users SET role = 'user' WHERE role = 'client'"))
            db.session.execute(text("UPDATE users SET role = 'user' WHERE role = 'employer'"))
            db.session.execute(
                text(
                    "ALTER TABLE users MODIFY COLUMN role "
                    "ENUM('admin', 'user') NOT NULL DEFAULT 'user'"
                )
            )
            db.session.commit()
            inspector = inspect(db.engine)

        if _column_exists(inspector, "jobs", "client_id") and not _column_exists(
            inspector, "jobs", "posted_by_id"
        ):
            db.session.execute(
                text("ALTER TABLE jobs CHANGE COLUMN client_id posted_by_id INT NOT NULL")
            )
        elif _column_exists(inspector, "jobs", "employer_id") and not _column_exists(
            inspector, "jobs", "posted_by_id"
        ):
            db.session.execute(
                text("ALTER TABLE jobs CHANGE COLUMN employer_id posted_by_id INT NOT NULL")
            )

        db.session.commit()
        print("Migration complete: user roles collapsed and jobs.posted_by_id set.")


if __name__ == "__main__":
    run_migration()
