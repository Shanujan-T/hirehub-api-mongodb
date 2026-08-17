"""Add phone/email OTP identity verification fields."""

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

        if not _column_exists(inspector, "users", "phone_number"):
            db.session.execute(text("ALTER TABLE users ADD COLUMN phone_number VARCHAR(32) NULL"))
        if not _column_exists(inspector, "users", "phone_verified_at"):
            db.session.execute(text("ALTER TABLE users ADD COLUMN phone_verified_at DATETIME NULL"))
        if not _column_exists(inspector, "users", "email_verified_at"):
            db.session.execute(text("ALTER TABLE users ADD COLUMN email_verified_at DATETIME NULL"))

        if not _table_exists(inspector, "verification_otps"):
            db.session.execute(
                text(
                    """
                    CREATE TABLE verification_otps (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL,
                        purpose VARCHAR(32) NOT NULL,
                        code_hash VARCHAR(255) NOT NULL,
                        expires_at DATETIME NOT NULL,
                        created_at DATETIME NOT NULL,
                        INDEX ix_verification_otps_user_id (user_id),
                        CONSTRAINT fk_verification_otps_user
                            FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                    """
                )
            )

        db.session.commit()
        print("Migration complete: OTP phone/email identity fields added.")

        db.session.execute(
            text(
                "UPDATE users SET identity_status = 'unverified' "
                "WHERE identity_status IN ('pending', 'rejected') AND nic_number IS NULL"
            )
        )
        db.session.commit()
        print("Reset non-NIC pending/rejected users to unverified for OTP flow.")


if __name__ == "__main__":
    run_migration()
