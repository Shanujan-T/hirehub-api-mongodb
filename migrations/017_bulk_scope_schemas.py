"""Upsert scope schemas for all bulk-seeded categories (extends 016)."""

from app import create_app
from seeders.seed_scope_schemas import apply_historical_jobs, apply_scope_schemas
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        schemas = apply_scope_schemas()
        jobs = apply_historical_jobs()
        db.session.commit()
        print(
            f"Migration complete: 017_bulk_scope_schemas "
            f"(schemas={schemas}, historical_jobs={jobs})."
        )


if __name__ == "__main__":
    run_migration()
