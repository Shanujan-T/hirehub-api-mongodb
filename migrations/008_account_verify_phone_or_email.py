"""Align account verification status when either phone or email OTP is confirmed."""

from sqlalchemy import text

from app import create_app
from app.extensions import db


def run_migration():
    app = create_app()
    with app.app_context():
        db.session.execute(
            text(
                "UPDATE users SET identity_status = 'verified' "
                "WHERE identity_status = 'unverified' "
                "AND (phone_verified_at IS NOT NULL OR email_verified_at IS NOT NULL)"
            )
        )
        db.session.commit()
        print("Migration complete: verified users with one OTP method.")


if __name__ == "__main__":
    run_migration()
