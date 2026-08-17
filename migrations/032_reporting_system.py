"""Upgrade legacy contract disputes to target-based moderation reports (MySQL)."""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db
from app.models.report_model import Report


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if "reports" not in inspector.get_table_names():
            Report.__table__.create(db.engine, checkfirst=True)
            return
        columns = {column["name"] for column in inspector.get_columns("reports")}
        if {"target_type", "target_id", "reporter_role", "resolved_at"}.issubset(columns):
            return
        if db.engine.dialect.name != "mysql":
            raise RuntimeError("Legacy reports migration is supported on the production MySQL database only.")

        additions = {
            "reporter_role": "VARCHAR(32) NULL",
            "target_type": "ENUM('user','employer','community') NULL",
            "target_id": "INT NULL",
            "description": "TEXT NULL",
            "evidence_url": "VARCHAR(512) NULL",
            "resolution_notes": "TEXT NULL",
            "resolved_by": "INT NULL",
            "resolved_at": "DATETIME NULL",
        }
        for name, definition in additions.items():
            if name not in columns:
                db.session.execute(text(f"ALTER TABLE reports ADD COLUMN {name} {definition}"))

        # Preserve legacy free-text reasons as descriptions and infer the closest target.
        db.session.execute(text("UPDATE reports SET description = reason WHERE description IS NULL"))
        db.session.execute(text("""
            UPDATE reports r
            JOIN users u ON u.id = r.reporter_id
            LEFT JOIN contracts c ON c.id = r.contract_id
            LEFT JOIN jobs j ON j.id = c.job_id
            SET r.reporter_role = u.role,
                r.target_type = CASE WHEN c.community_id IS NOT NULL THEN 'community' ELSE 'user' END,
                r.target_id = COALESCE(c.community_id, j.posted_by_id, r.reporter_id)
        """))
        db.session.execute(text("UPDATE reports SET reason = 'other'"))
        db.session.execute(text("""
            ALTER TABLE reports
              MODIFY reporter_role VARCHAR(32) NOT NULL,
              MODIFY target_type ENUM('user','employer','community') NOT NULL,
              MODIFY target_id INT NOT NULL,
              MODIFY reason ENUM('fraud_or_scam','no_show_or_abandoned_job','harassment_or_abuse',
                'fake_profile','unsafe_behavior','payment_dispute','inappropriate_content','other') NOT NULL,
              MODIFY status ENUM('open','under_review','resolved','dismissed') NOT NULL DEFAULT 'open',
              ADD CONSTRAINT fk_reports_resolved_by FOREIGN KEY (resolved_by) REFERENCES users(id),
              ADD INDEX ix_reports_filters (status, target_type, reason),
              ADD INDEX ix_reports_reporter_created (reporter_id, created_at)
        """))
        db.session.commit()
        print("Migration complete: target-based reporting system installed.")


if __name__ == "__main__":
    run_migration()
