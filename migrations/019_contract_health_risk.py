"""Add contract risk_level / risk_reason / risk_flags / risk_checked_at."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "contracts" not in inspector.get_table_names():
            print("Skip: contracts table missing.")
            return

        columns = {col["name"] for col in inspector.get_columns("contracts")}
        dialect = db.engine.dialect.name

        if "risk_level" not in columns:
            if dialect == "mysql":
                db.session.execute(
                    text(
                        "ALTER TABLE contracts ADD COLUMN risk_level "
                        "ENUM('none','low','high') NOT NULL DEFAULT 'none'"
                    )
                )
            else:
                db.session.execute(
                    text(
                        "ALTER TABLE contracts ADD COLUMN risk_level VARCHAR(10) "
                        "NOT NULL DEFAULT 'none'"
                    )
                )
            print("Added contracts.risk_level")
        else:
            print("Skip: contracts.risk_level already exists.")

        if "risk_reason" not in columns:
            db.session.execute(text("ALTER TABLE contracts ADD COLUMN risk_reason TEXT NULL"))
            print("Added contracts.risk_reason")
        else:
            print("Skip: contracts.risk_reason already exists.")

        if "risk_flags" not in columns:
            db.session.execute(
                text("ALTER TABLE contracts ADD COLUMN risk_flags VARCHAR(255) NULL")
            )
            print("Added contracts.risk_flags")
        else:
            print("Skip: contracts.risk_flags already exists.")

        if "risk_checked_at" not in columns:
            if dialect == "mysql":
                db.session.execute(
                    text("ALTER TABLE contracts ADD COLUMN risk_checked_at DATETIME NULL")
                )
            else:
                db.session.execute(
                    text("ALTER TABLE contracts ADD COLUMN risk_checked_at TIMESTAMP NULL")
                )
            print("Added contracts.risk_checked_at")
        else:
            print("Skip: contracts.risk_checked_at already exists.")

        db.session.commit()
        print("Migration complete: 019_contract_health_risk.")


if __name__ == "__main__":
    run_migration()
