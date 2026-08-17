"""Reintroduce employer accounts for community members and workers.

The deliberately named ``user`` role posts jobs; ``employer`` does the work.
Existing accounts with community membership rows are the only accounts backfilled.
"""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        role_column = next(
            (column for column in inspector.get_columns("users") if column["name"] == "role"),
            None,
        )
        role_type = str(role_column.get("type", "")) if role_column else ""

        if db.engine.dialect.name == "mysql" and "employer" not in role_type:
            db.session.execute(
                text(
                    "ALTER TABLE users MODIFY COLUMN role "
                    "ENUM('admin', 'user', 'employer') NOT NULL DEFAULT 'user'"
                )
            )

        # These rows demonstrably belong to the community/work side of the demo flow.
        db.session.execute(
            text(
                "UPDATE users SET role = 'employer' "
                "WHERE role = 'user' AND id IN "
                "(SELECT DISTINCT user_id FROM community_members)"
            )
        )
        db.session.commit()
        print("Migration complete: employer role restored and community accounts backfilled.")


if __name__ == "__main__":
    run_migration()
