import pytest

from app import create_app
from app.config import Config
from app.extensions import db


@pytest.fixture()
def client():
    Config.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    Config.SQLALCHEMY_ENGINE_OPTIONS = {}
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def test_register_then_login(client):
    registered = client.post("/api/auth/register", json={
        "email": " New.User@Example.com ",
        "password": "secret123",
        "full_name": " New User ",
        "role": "user",
    })
    assert registered.status_code == 201
    assert registered.json["user"]["email"] == "new.user@example.com"
    assert registered.json["access_token"]

    logged_in = client.post("/api/auth/login", json={
        "email": " NEW.USER@example.com ",
        "password": "secret123",
    })
    assert logged_in.status_code == 200
    assert logged_in.json["user"]["email"] == "new.user@example.com"


def test_duplicate_email_is_case_insensitive(client):
    payload = {"email": "person@example.com", "password": "secret123", "full_name": "Person", "role": "employer"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    payload["email"] = "PERSON@EXAMPLE.COM"
    assert client.post("/api/auth/register", json=payload).status_code == 409
