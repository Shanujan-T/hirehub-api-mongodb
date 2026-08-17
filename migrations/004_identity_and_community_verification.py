"""Add user identity verification and community manual review fields."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def _column_exists(inspector, table_name, column_name):
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)

        if not _column_exists(inspector, "users", "nic_number"):
            db.session.execute(text("ALTER TABLE users ADD COLUMN nic_number VARCHAR(512) NULL"))
        if not _column_exists(inspector, "users", "nic_document_url"):
            db.session.execute(text("ALTER TABLE users ADD COLUMN nic_document_url VARCHAR(512) NULL"))
        if not _column_exists(inspector, "users", "identity_status"):
            db.session.execute(
                text(
                    "ALTER TABLE users ADD COLUMN identity_status "
                    "ENUM('unverified', 'pending', 'verified', 'rejected') "
                    "NOT NULL DEFAULT 'unverified'"
                )
            )
        if not _column_exists(inspector, "users", "identity_rejection_reason"):
            db.session.execute(text("ALTER TABLE users ADD COLUMN identity_rejection_reason TEXT NULL"))

        if not _column_exists(inspector, "communities", "category_id"):
            db.session.execute(text("ALTER TABLE communities ADD COLUMN category_id INT NULL"))
        db.session.execute(text("UPDATE communities SET category_id = 1 WHERE category_id IS NULL"))

        if not _column_exists(inspector, "communities", "experience_level"):
            db.session.execute(
                text(
                    "ALTER TABLE communities ADD COLUMN experience_level "
                    "ENUM('less_than_1_year', '1_to_3_years', '3_plus_years') NULL"
                )
            )
        db.session.execute(
            text("UPDATE communities SET experience_level = '1_to_3_years' WHERE experience_level IS NULL")
        )

        if not _column_exists(inspector, "communities", "specialization"):
            db.session.execute(text("ALTER TABLE communities ADD COLUMN specialization VARCHAR(255) NULL"))
        if not _column_exists(inspector, "communities", "portfolio_links"):
            db.session.execute(text("ALTER TABLE communities ADD COLUMN portfolio_links JSON NULL"))
        if not _column_exists(inspector, "communities", "admin_bio"):
            db.session.execute(text("ALTER TABLE communities ADD COLUMN admin_bio TEXT NULL"))
        if not _column_exists(inspector, "communities", "contact_phone"):
            db.session.execute(text("ALTER TABLE communities ADD COLUMN contact_phone VARCHAR(64) NULL"))

        if not _column_exists(inspector, "communities", "status"):
            db.session.execute(
                text(
                    "ALTER TABLE communities ADD COLUMN status "
                    "ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending'"
                )
            )
            db.session.execute(text("UPDATE communities SET status = 'approved'"))
        if not _column_exists(inspector, "communities", "rejection_reason"):
            db.session.execute(text("ALTER TABLE communities ADD COLUMN rejection_reason TEXT NULL"))

        db.session.commit()
        print("Migration complete: identity and community verification fields added.")


if __name__ == "__main__":
    run_migration()
