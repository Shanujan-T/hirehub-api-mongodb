"""Add baseline_scope_key to categories and drop baseline_unit."""

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
        
        # 1. Add baseline_scope_key column if not exists
        if "baseline_scope_key" not in columns:
            db.session.execute(text("ALTER TABLE categories ADD COLUMN baseline_scope_key VARCHAR(64) NULL"))
            print("Added categories.baseline_scope_key")
        else:
            print("Skip: categories.baseline_scope_key already exists.")

        # 2. If baseline_unit column exists, run data migration and then drop baseline_unit
        if "baseline_unit" in columns:
            # Data migration
            db.session.execute(text("UPDATE categories SET baseline_scope_key = 'area_sqft' WHERE baseline_unit = 'per_sqft'"))
            db.session.execute(text("UPDATE categories SET baseline_scope_key = 'word_count' WHERE baseline_unit = 'per_word'"))
            db.session.execute(text("UPDATE categories SET baseline_scope_key = 'hours' WHERE baseline_unit = 'per_hour'"))
            db.session.commit()
            print("Migrated baseline_unit values to baseline_scope_key.")

            # Drop baseline_unit column
            try:
                db.session.execute(text("ALTER TABLE categories DROP COLUMN baseline_unit"))
                print("Dropped categories.baseline_unit")
            except Exception as e:
                # If DROP COLUMN is not supported (e.g. older SQLite), ignore or handle it
                print("Note: ALTER TABLE categories DROP COLUMN baseline_unit failed (may not be supported on this SQLite version).", e)
        else:
            print("Skip: categories.baseline_unit already dropped.")

        db.session.commit()
        print("Migration complete: 026_category_baseline_scope_key.")

if __name__ == "__main__":
    run_migration()
