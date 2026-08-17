"""Add an optional event time for photography jobs."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        columns = {column["name"] for column in inspect(db.engine).get_columns("jobs")}
        if "event_time" in columns:
            print("Skip: jobs.event_time already exists.")
            return
        db.session.execute(text("ALTER TABLE jobs ADD COLUMN event_time TIME NULL"))
        db.session.commit()
        print("Added jobs.event_time.")


if __name__ == "__main__":
    run_migration()
