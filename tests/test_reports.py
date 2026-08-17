import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.config import Config
from app.extensions import db
from app.models.report_model import Report
from app.models.user_model import User


@pytest.fixture()
def app(monkeypatch):
    Config.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    Config.SQLALCHEMY_ENGINE_OPTIONS = {}
    monkeypatch.setattr("app.controllers.report_controller._notify_admins", lambda report: None)
    application = create_app()
    application.config.update(TESTING=True)
    with application.app_context():
        db.drop_all()
        db.create_all()
        reporter = User(email="reporter@example.com", full_name="Reporter", role="user", password="x")
        target = User(email="worker@example.com", full_name="Worker", role="employer", password="x")
        admin = User(email="admin@example.com", full_name="Admin", role="admin", password="x")
        outsider = User(email="other@example.com", full_name="Other", role="user", password="x")
        db.session.add_all([reporter, target, admin, outsider])
        db.session.commit()
        application.config["ids"] = {u.role if u.role == "admin" else u.email: u.id for u in (reporter, target, admin, outsider)}
        application.config["tokens"] = {key: create_access_token(identity=str(value)) for key, value in application.config["ids"].items()}
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def auth(app, key):
    return {"Authorization": f"Bearer {app.config['tokens'][key]}"}


def payload(app, reason="fraud_or_scam"):
    return {"target_type": "employer", "target_id": app.config["ids"]["worker@example.com"], "reason": reason, "description": "Details"}


def test_filing_report_uses_jwt_identity(client, app):
    body = payload(app)
    body["reporter_id"] = app.config["ids"]["other@example.com"]
    response = client.post("/api/reports", json=body, headers=auth(app, "reporter@example.com"))
    assert response.status_code == 201
    with app.app_context():
        assert Report.query.one().reporter_id == app.config["ids"]["reporter@example.com"]


def test_duplicate_open_report_is_blocked(client, app):
    headers = auth(app, "reporter@example.com")
    assert client.post("/api/reports", json=payload(app), headers=headers).status_code == 201
    assert client.post("/api/reports", json=payload(app), headers=headers).status_code == 409


def test_rate_limit_enforced(client, app):
    headers = auth(app, "reporter@example.com")
    reasons = ["fraud_or_scam", "no_show_or_abandoned_job", "harassment_or_abuse", "fake_profile", "unsafe_behavior"]
    for reason in reasons:
        assert client.post("/api/reports", json=payload(app, reason), headers=headers).status_code == 201
    assert client.post("/api/reports", json=payload(app, "payment_dispute"), headers=headers).status_code == 429


@pytest.mark.parametrize("method,path", [("get", "/api/reports"), ("get", "/api/reports/1"), ("patch", "/api/reports/1")])
def test_admin_endpoints_reject_non_admin(client, app, method, path):
    response = getattr(client, method)(path, json={} if method == "patch" else None, headers=auth(app, "reporter@example.com"))
    assert response.status_code == 403


def test_admin_can_list_detail_and_update(client, app):
    client.post("/api/reports", json=payload(app), headers=auth(app, "reporter@example.com"))
    headers = auth(app, "admin")
    listing = client.get("/api/reports?status=open&per_page=10", headers=headers)
    assert listing.status_code == 200
    assert listing.json["reports"][0]["reporter"]["email"] == "reporter@example.com"
    assert client.get("/api/reports/1", headers=headers).status_code == 200
    updated = client.patch("/api/reports/1", json={"status": "resolved", "resolution_notes": "Reviewed"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json["report"]["resolved_by"] == app.config["ids"]["admin"]


def test_mine_hides_reporter_identity(client, app):
    client.post("/api/reports", json=payload(app), headers=auth(app, "reporter@example.com"))
    response = client.get("/api/reports/mine", headers=auth(app, "reporter@example.com"))
    assert response.status_code == 200
    report = response.json["reports"][0]
    assert "reporter" not in report
    assert "reporter_id" not in report
