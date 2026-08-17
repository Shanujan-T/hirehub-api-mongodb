"""Rename employer role to client and jobs.employer_id to client_id."""

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
    col_type = str(role_col.get("type", ""))
    return value in col_type


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)

        # Step 1: add 'client' to enum before updating rows (MySQL rejects unknown enum values)
        if _role_enum_includes(inspector, "employer") and not _role_enum_includes(
            inspector, "client"
        ):
            db.session.execute(
                text(
                    "ALTER TABLE users MODIFY COLUMN role "
                    "ENUM('admin', 'employer', 'client', 'user') NOT NULL DEFAULT 'user'"
                )
            )
            db.session.commit()
            inspector = inspect(db.engine)

        if _role_enum_includes(inspector, "employer"):
            db.session.execute(text("UPDATE users SET role = 'client' WHERE role = 'employer'"))
            db.session.execute(
                text(
                    "ALTER TABLE users MODIFY COLUMN role "
                    "ENUM('admin', 'client', 'user') NOT NULL DEFAULT 'user'"
                )
            )

        if _column_exists(inspector, "jobs", "employer_id") and not _column_exists(
            inspector, "jobs", "client_id"
        ):
            db.session.execute(
                text("ALTER TABLE jobs CHANGE COLUMN employer_id client_id INT NOT NULL")
            )

        db.session.commit()
        print("Migration complete: employer role/column renamed to client.")


if __name__ == "__main__":
    run_migration()
