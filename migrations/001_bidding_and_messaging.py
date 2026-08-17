"""Apply bidding + messaging schema changes."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def _column_exists(inspector, table_name, column_name):
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _table_exists(inspector, table_name):
    return table_name in inspector.get_table_names()


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)

        if _table_exists(inspector, "community_applications"):
            if not _column_exists(inspector, "community_applications", "proposed_cost"):
                db.session.execute(
                    text(
                        "ALTER TABLE community_applications "
                        "ADD COLUMN proposed_cost DECIMAL(10, 2) NOT NULL DEFAULT 1"
                    )
                )
            if not _column_exists(inspector, "community_applications", "proposed_days"):
                db.session.execute(
                    text(
                        "ALTER TABLE community_applications "
                        "ADD COLUMN proposed_days INT NOT NULL DEFAULT 1"
                    )
                )
            if not _column_exists(inspector, "community_applications", "note"):
                db.session.execute(
                    text("ALTER TABLE community_applications ADD COLUMN note TEXT NULL")
                )

            db.session.execute(
                text(
                    "UPDATE community_applications ca "
                    "JOIN jobs j ON j.id = ca.job_id "
                    "SET ca.proposed_cost = j.final_price "
                    "WHERE ca.proposed_cost IS NULL OR ca.proposed_cost <= 0"
                )
            )
            db.session.execute(
                text(
                    "UPDATE community_applications "
                    "SET proposed_days = 7 "
                    "WHERE proposed_days IS NULL OR proposed_days <= 0"
                )
            )

        if not _table_exists(inspector, "conversations"):
            db.session.execute(
                text(
                    "CREATE TABLE conversations ("
                    "id INT AUTO_INCREMENT PRIMARY KEY,"
                    "contract_id INT NOT NULL UNIQUE,"
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                    "CONSTRAINT fk_conversations_contract "
                    "FOREIGN KEY (contract_id) REFERENCES contracts(id)"
                    ")"
                )
            )

        if not _table_exists(inspector, "messages"):
            db.session.execute(
                text(
                    "CREATE TABLE messages ("
                    "id INT AUTO_INCREMENT PRIMARY KEY,"
                    "conversation_id INT NOT NULL,"
                    "sender_id INT NOT NULL,"
                    "content TEXT NOT NULL,"
                    "read_at DATETIME NULL,"
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                    "CONSTRAINT fk_messages_conversation "
                    "FOREIGN KEY (conversation_id) REFERENCES conversations(id),"
                    "CONSTRAINT fk_messages_sender "
                    "FOREIGN KEY (sender_id) REFERENCES users(id)"
                    ")"
                )
            )

        db.session.execute(
            text(
                "INSERT INTO conversations (contract_id, created_at) "
                "SELECT c.id, COALESCE(c.created_at, CURRENT_TIMESTAMP) "
                "FROM contracts c "
                "LEFT JOIN conversations conv ON conv.contract_id = c.id "
                "WHERE conv.id IS NULL"
            )
        )

        db.session.commit()
        db.create_all()
        print("Migration complete: bidding fields, conversations, messages.")


if __name__ == "__main__":
    run_migration()
