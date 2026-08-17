"""Add category request/approval fields: status, requested_by_id, request_description, rejection_reason."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "categories" not in inspector.get_table_names():
            print("Skip: categories table missing.")
            return

        columns = {col["name"] for col in inspector.get_columns("categories")}
        dialect = db.engine.dialect.name

        if "status" not in columns:
            if dialect == "mysql":
                db.session.execute(
                    text(
                        "ALTER TABLE categories ADD COLUMN status "
                        "ENUM('pending','approved','rejected') NOT NULL DEFAULT 'approved'"
                    )
                )
            else:
                db.session.execute(
                    text(
                        "ALTER TABLE categories ADD COLUMN status "
                        "VARCHAR(20) NOT NULL DEFAULT 'approved'"
                    )
                )
            print("Added categories.status")
        else:
            print("Skip: categories.status already exists.")

        if "requested_by_id" not in columns:
            db.session.execute(
                text("ALTER TABLE categories ADD COLUMN requested_by_id INT NULL")
            )
            print("Added categories.requested_by_id")
        else:
            print("Skip: categories.requested_by_id already exists.")

        if "request_description" not in columns:
            db.session.execute(
                text("ALTER TABLE categories ADD COLUMN request_description TEXT NULL")
            )
            print("Added categories.request_description")
        else:
            print("Skip: categories.request_description already exists.")

        if "rejection_reason" not in columns:
            db.session.execute(
                text("ALTER TABLE categories ADD COLUMN rejection_reason TEXT NULL")
            )
            print("Added categories.rejection_reason")
        else:
            print("Skip: categories.rejection_reason already exists.")

        db.session.commit()

        # Explicitly approve all existing rows (self-documenting migration of legacy data)
        result = db.session.execute(
            text("UPDATE categories SET status = 'approved' WHERE status IS NULL OR status = '' OR status = 'approved'")
        )
        # Also force-approve anything that somehow isn't pending/rejected yet from pre-feature data:
        # All current rows should be approved.
        db.session.execute(text("UPDATE categories SET status = 'approved' WHERE status NOT IN ('pending', 'rejected')"))
        db.session.commit()
        print(f"Ensured existing categories are approved (rowcount={result.rowcount}).")

        # FK if supported and not present
        try:
            fks = {fk["constrained_columns"][0] for fk in inspector.get_foreign_keys("categories") if fk.get("constrained_columns")}
        except Exception:
            fks = set()
        if "requested_by_id" not in fks and dialect == "mysql":
            try:
                db.session.execute(
                    text(
                        "ALTER TABLE categories ADD CONSTRAINT fk_categories_requested_by "
                        "FOREIGN KEY (requested_by_id) REFERENCES users(id)"
                    )
                )
                db.session.commit()
                print("Added FK categories.requested_by_id -> users.id")
            except Exception as exc:
                db.session.rollback()
                print(f"Skip FK (may already exist): {exc}")

        print("Migration complete: 015_category_requests.")


if __name__ == "__main__":
    run_migration()
