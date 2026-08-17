"""Create ai_review_digests cache table (regenerated on new reviews)."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "ai_review_digests" in inspector.get_table_names():
            print("Skip: ai_review_digests table already exists.")
            return

        db.session.execute(
            text(
                """
                CREATE TABLE ai_review_digests (
                    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    community_id INT NOT NULL,
                    praised_json TEXT NOT NULL,
                    flagged_json TEXT NOT NULL,
                    review_count INT NOT NULL DEFAULT 0,
                    updated_at DATETIME NOT NULL,
                    UNIQUE KEY uq_ai_review_digest_community (community_id),
                    CONSTRAINT fk_ai_digest_community FOREIGN KEY (community_id)
                        REFERENCES communities(id) ON DELETE CASCADE
                )
                """
            )
        )
        db.session.commit()
        print("Migration complete: ai_review_digests table created.")


if __name__ == "__main__":
    run_migration()
