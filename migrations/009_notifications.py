"""Create notifications table for in-app alerts."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "notifications" in inspector.get_table_names():
            print("Skip: notifications table already exists.")
            return

        db.session.execute(
            text(
                """
                CREATE TABLE notifications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    type VARCHAR(64) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    body TEXT NOT NULL,
                    link_href VARCHAR(512) NULL,
                    read_at DATETIME NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX ix_notifications_user_id (user_id),
                    CONSTRAINT fk_notifications_user_id
                        FOREIGN KEY (user_id) REFERENCES users(id)
                        ON DELETE CASCADE
                )
                """
            )
        )
        db.session.commit()
        print("Migration complete: notifications table created.")


if __name__ == "__main__":
    run_migration()
