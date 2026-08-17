"""Create ai_match_blurbs cache table for job↔community AI blurbs."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "ai_match_blurbs" in inspector.get_table_names():
            print("Skip: ai_match_blurbs table already exists.")
            return

        db.session.execute(
            text(
                """
                CREATE TABLE ai_match_blurbs (
                    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    job_id INT NOT NULL,
                    community_id INT NOT NULL,
                    blurb TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    UNIQUE KEY uq_ai_match_job_community (job_id, community_id),
                    CONSTRAINT fk_ai_blurb_job FOREIGN KEY (job_id) REFERENCES jobs(id)
                        ON DELETE CASCADE,
                    CONSTRAINT fk_ai_blurb_community FOREIGN KEY (community_id) REFERENCES communities(id)
                        ON DELETE CASCADE
                )
                """
            )
        )
        db.session.commit()
        print("Migration complete: ai_match_blurbs table created.")
