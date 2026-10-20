from __future__ import annotations

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import OwnerUser
from app.services import auth_service


@pytest.fixture()
def app(monkeypatch):
    application = create_app(TestConfig)
    for table in db.metadata.tables.values():
        table.schema = None

    outbox = []

    def fake_send(recipient, code, purpose="password_reset"):
        outbox.append((recipient, code, purpose))

    monkeypatch.setattr("app.services.auth_service.send_verification_email", fake_send)
    monkeypatch.setattr(
        "app.services.auth_service.send_password_changed_email",
        lambda *args, **kwargs: None,
    )

    with application.app_context():
        db.create_all()
        application.extensions["mail_outbox"] = outbox
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _owner(email="owner@example.com"):
    user = OwnerUser(
        email=email,
        password_hash=generate_password_hash("secure-password-12", method="scrypt"),
        full_name="Owner",
        role="owner",
        status="active",
        email_verified=True,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    return user


def test_forgot_password_missing_account(client):
    response = client.post("/forgot-password", data={"email": "nobody@example.com"})
    assert response.status_code == 200
    assert b"No Owner account with credentials" in response.data


def test_password_reset_flow(client, app):
    with app.app_context():
        _owner()

    start = client.post(
        "/forgot-password",
        data={"email": "owner@example.com"},
        follow_redirects=False,
    )
    assert start.status_code in {302, 303}
    assert "/verify-reset-code" in (start.headers.get("Location") or "")

    with app.app_context():
        code = app.extensions["mail_outbox"][-1][1]

    verify = client.post(
        "/verify-reset-code",
        data={"action": "verify", "code": code},
        follow_redirects=False,
    )
    assert verify.status_code in {302, 303}
    assert "/reset-password" in (verify.headers.get("Location") or "")

    reset = client.post(
        "/reset-password",
        data={"password": "brand-new-pass-99", "confirm": "brand-new-pass-99"},
        follow_redirects=False,
    )
    assert reset.status_code in {302, 303}
    assert "/login" in (reset.headers.get("Location") or "")

    with app.app_context():
        user = OwnerUser.query.filter_by(email="owner@example.com").one()
        assert check_password_hash(user.password_hash, "brand-new-pass-99")
        assert not check_password_hash(user.password_hash, "secure-password-12")


def test_resend_cooldown(client, app):
    with app.app_context():
        user = _owner("cooldown@example.com")
        auth_service.issue_and_send_code(user, auth_service.PURPOSE_RESET)

    with client.session_transaction() as sess:
        with app.app_context():
            user = OwnerUser.query.filter_by(email="cooldown@example.com").one()
            sess["reset_user_id"] = user.id

    again = client.post("/verify-reset-code", data={"action": "resend"})
    assert again.status_code == 200
    assert b"Wait before requesting another code" in again.data
