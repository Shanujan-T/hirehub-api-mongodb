"""Add community_applications.source (applied | invited)."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "community_applications" not in inspector.get_table_names():
            print("Skip: community_applications table missing.")
            return

        columns = {col["name"] for col in inspector.get_columns("community_applications")}
        dialect = db.engine.dialect.name

        if "source" not in columns:
            if dialect == "mysql":
                db.session.execute(
                    text(
                        "ALTER TABLE community_applications ADD COLUMN source "
                        "ENUM('applied','invited') NOT NULL DEFAULT 'applied'"
                    )
                )
            else:
                db.session.execute(
                    text(
                        "ALTER TABLE community_applications ADD COLUMN source VARCHAR(20) "
                        "NOT NULL DEFAULT 'applied'"
                    )
                )
            print("Added community_applications.source")
        else:
            print("Skip: community_applications.source already exists.")

        db.session.commit()
        print("Migration complete: 021_community_application_source.")


if __name__ == "__main__":
    run_migration()
