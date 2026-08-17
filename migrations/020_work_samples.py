"""Create work_samples table for AI skill verification."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        if "work_samples" in tables:
            print("Skip: work_samples already exists.")
            db.session.commit()
            print("Migration complete: 020_work_samples.")
            return

        dialect = db.engine.dialect.name
        if dialect == "mysql":
            db.session.execute(
                text(
                    """
                    CREATE TABLE work_samples (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_skill_id INT NOT NULL,
                        sample_type ENUM('text','image') NOT NULL,
                        content TEXT NOT NULL,
                        ai_assessment TEXT NULL,
                        verification_status ENUM('unreviewed','plausible','unclear')
                            NOT NULL DEFAULT 'unreviewed',
                        created_at DATETIME NOT NULL,
                        CONSTRAINT fk_work_samples_user_skill
                            FOREIGN KEY (user_skill_id) REFERENCES user_skills(id)
                            ON DELETE CASCADE
                    )
                    """
                )
            )
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE work_samples (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_skill_id INTEGER NOT NULL,
                        sample_type VARCHAR(20) NOT NULL,
                        content TEXT NOT NULL,
                        ai_assessment TEXT NULL,
                        verification_status VARCHAR(20) NOT NULL DEFAULT 'unreviewed',
                        created_at TIMESTAMP NOT NULL,
                        FOREIGN KEY (user_skill_id) REFERENCES user_skills(id)
                            ON DELETE CASCADE
                    )
                    """
                )
            )
        print("Created work_samples table")
        db.session.commit()
        print("Migration complete: 020_work_samples.")


if __name__ == "__main__":
    run_migration()
