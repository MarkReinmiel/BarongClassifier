from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import OwnerUser


@pytest.fixture()
def app(monkeypatch):
    application = create_app(TestConfig)
    for table in db.metadata.tables.values():
        table.schema = None

    monkeypatch.setattr(
        "app.services.auth_service.send_verification_email",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.auth_service.send_password_changed_email",
        lambda *args, **kwargs: None,
    )

    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _owner(**kwargs):
    defaults = {
        "email": "owner@example.com",
        "password_hash": generate_password_hash("secure-password-12", method="scrypt"),
        "full_name": "Owner",
        "role": "owner",
        "status": "active",
        "email_verified": True,
        "is_active": True,
    }
    defaults.update(kwargs)
    user = OwnerUser(**defaults)
    db.session.add(user)
    db.session.commit()
    return user


def test_owner_login_success(client, app):
    with app.app_context():
        _owner()
    response = client.post(
        "/login",
        data={"email": "owner@example.com", "password": "secure-password-12"},
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}
    assert "/dashboard" in (response.headers.get("Location") or "")


def test_wrong_password(client, app):
    with app.app_context():
        _owner()
    response = client.post(
        "/login",
        data={"email": "owner@example.com", "password": "wrong-password-12"},
    )
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_missing_email_generic(client):
    response = client.post(
        "/login",
        data={"email": "missing@example.com", "password": "secure-password-12"},
    )
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_customer_denied(client, app):
    with app.app_context():
        _owner(email="cust@example.com", role="customer")
    response = client.post(
        "/login",
        data={"email": "cust@example.com", "password": "secure-password-12"},
    )
    assert response.status_code == 200
    assert b"not authorized" in response.data


def test_dashboard_requires_login(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code in {302, 303}
    assert "/login" in (response.headers.get("Location") or "")
