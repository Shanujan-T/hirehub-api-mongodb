"""Add origin, payout_percent, and payout_amount to contract_applications."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "contract_applications" not in inspector.get_table_names():
            print("Skip: contract_applications table missing.")
            return

        columns = {col["name"] for col in inspector.get_columns("contract_applications")}
        dialect = db.engine.dialect.name

        if "origin" not in columns:
            if dialect == "mysql":
                db.session.execute(
                    text(
                        "ALTER TABLE contract_applications ADD COLUMN origin "
                        "ENUM('applied','direct_assign') NOT NULL DEFAULT 'applied'"
                    )
                )
            else:
                db.session.execute(
                    text(
                        "ALTER TABLE contract_applications ADD COLUMN origin VARCHAR(20) "
                        "NOT NULL DEFAULT 'applied'"
                    )
                )
            print("Added contract_applications.origin")
        else:
            print("Skip: contract_applications.origin already exists.")

        if "payout_percent" not in columns:
            if dialect == "mysql":
                db.session.execute(
                    text(
                        "ALTER TABLE contract_applications ADD COLUMN payout_percent "
                        "DECIMAL(5,2) DEFAULT NULL"
                    )
                )
            else:
                db.session.execute(
                    text(
                        "ALTER TABLE contract_applications ADD COLUMN payout_percent "
                        "NUMERIC(5,2) DEFAULT NULL"
                    )
                )
            print("Added contract_applications.payout_percent")
        else:
            print("Skip: contract_applications.payout_percent already exists.")

        if "payout_amount" not in columns:
            if dialect == "mysql":
                db.session.execute(
                    text(
                        "ALTER TABLE contract_applications ADD COLUMN payout_amount "
                        "DECIMAL(10,2) DEFAULT NULL"
                    )
                )
            else:
                db.session.execute(
                    text(
                        "ALTER TABLE contract_applications ADD COLUMN payout_amount "
                        "NUMERIC(10,2) DEFAULT NULL"
                    )
                )
            print("Added contract_applications.payout_amount")
        else:
            print("Skip: contract_applications.payout_amount already exists.")

        db.session.commit()
        print("Migration complete: 025_contract_application_origin_and_payout.")


if __name__ == "__main__":
    run_migration()
