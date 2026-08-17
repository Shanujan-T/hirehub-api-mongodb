"""Add categories.baseline_price and baseline_unit."""

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

        if "baseline_price" not in columns:
            if dialect == "mysql":
                db.session.execute(
                    text(
                        "ALTER TABLE categories ADD COLUMN baseline_price DECIMAL(12, 2) NULL"
                    )
                )
            else:
                db.session.execute(
                    text("ALTER TABLE categories ADD COLUMN baseline_price NUMERIC(12, 2) NULL")
                )
            print("Added categories.baseline_price")
        else:
            print("Skip: categories.baseline_price already exists.")

        if "baseline_unit" not in columns:
            if dialect == "mysql":
                db.session.execute(
                    text(
                        "ALTER TABLE categories ADD COLUMN baseline_unit "
                        "ENUM('per_job','per_sqft') NULL"
                    )
                )
            else:
                db.session.execute(
                    text("ALTER TABLE categories ADD COLUMN baseline_unit VARCHAR(20) NULL")
                )
            print("Added categories.baseline_unit")
        else:
            print("Skip: categories.baseline_unit already exists.")

        db.session.commit()
        print("Migration complete: 018_category_baseline_price.")


if __name__ == "__main__":
    run_migration()
