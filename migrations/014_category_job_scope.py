"""Add categories.scope_schema and jobs.scope_data JSON columns."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())

        if "categories" in tables:
            columns = {col["name"] for col in inspector.get_columns("categories")}
            if "scope_schema" not in columns:
                db.session.execute(
                    text("ALTER TABLE categories ADD COLUMN scope_schema TEXT NULL")
                )
                print("Added categories.scope_schema")
            else:
                print("Skip: categories.scope_schema already exists.")
        else:
            print("Skip: categories table missing.")

        if "jobs" in tables:
            columns = {col["name"] for col in inspector.get_columns("jobs")}
            if "scope_data" not in columns:
                db.session.execute(text("ALTER TABLE jobs ADD COLUMN scope_data TEXT NULL"))
                print("Added jobs.scope_data")
            else:
                print("Skip: jobs.scope_data already exists.")
        else:
            print("Skip: jobs table missing.")

        db.session.commit()
        print("Migration complete: 014_category_job_scope.")


if __name__ == "__main__":
    run_migration()
