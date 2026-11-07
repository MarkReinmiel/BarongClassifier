from __future__ import annotations

from datetime import timedelta

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import CustomerUser, EmailVerification, PendingSignup, utcnow
from app.services import auth_service
from app.utils.security import hash_secret
from werkzeug.security import generate_password_hash


@pytest.fixture()
def app(monkeypatch):
    application = create_app(TestConfig)

    for table in db.metadata.tables.values():
        table.schema = None

    sent = []

    def fake_send(recipient, code, purpose="registration"):
        sent.append((recipient, code, purpose))

    monkeypatch.setattr("app.services.auth_service.send_verification_email", fake_send)
    monkeypatch.setattr("app.services.email_service.send_verification_email", fake_send)

    with application.app_context():
        db.create_all()
        application.extensions["mail_outbox"] = sent
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def test_register_and_verify(client, app):
    response = client.post(
        "/auth/register",
        data={
            "email": "Customer@Example.com",
            "password": "secure-password-12",
            "confirm_password": "secure-password-12",
        },
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}
    with app.app_context():
        assert CustomerUser.query.filter_by(email="customer@example.com").first() is None
        pending = PendingSignup.query.filter_by(email="customer@example.com").one()
        assert pending.status == "pending"
        assert app.extensions["mail_outbox"]
        code = app.extensions["mail_outbox"][-1][1]

    with client.session_transaction() as sess:
        assert sess.get("pending_signup_id")

    verify = client.post(
        "/auth/verify-code",
        json={"code": code, "purpose": "registration"},
    )
    assert verify.status_code == 200
    assert verify.get_json()["verified"] is True
    with app.app_context():
        user = CustomerUser.query.filter_by(email="customer@example.com").one()
        assert user.email_verified is True
        assert user.status == "active"
        assert PendingSignup.query.filter_by(email="customer@example.com").first() is None


def test_resend_cooldown(client, app):
    client.post(
        "/auth/register",
        data={
            "email": "cooldown@example.com",
            "password": "secure-password-12",
            "confirm_password": "secure-password-12",
        },
    )
    again = client.post("/auth/resend-code", json={"purpose": "registration"})
    assert again.status_code == 429
    payload = again.get_json()
    assert payload["retry_after_seconds"] > 0

    status = client.get("/auth/verification-status?purpose=registration")
    assert status.status_code == 200
    assert status.get_json()["resend_after_seconds"] > 0


def test_login_missing_account_shows_error(client):
    response = client.post(
        "/auth/login",
        data={"email": "missing@example.com", "password": "secure-password-12"},
    )
    # Auth pages cap at 400 so hosts do not replace the body with a 5xx page.
    assert response.status_code == 400
    assert b"No account found for that email" in response.data


def test_register_unverified_can_retry_without_saving_user(client, app):
    client.post(
        "/auth/register",
        data={
            "email": "dup@example.com",
            "password": "secure-password-12",
            "confirm_password": "secure-password-12",
        },
    )
    with app.app_context():
        assert CustomerUser.query.filter_by(email="dup@example.com").first() is None
        assert PendingSignup.query.filter_by(email="dup@example.com").count() == 1

    again = client.post(
        "/auth/register",
        data={
            "email": "dup@example.com",
            "password": "secure-password-99",
            "confirm_password": "secure-password-99",
        },
        follow_redirects=False,
    )
    assert again.status_code in {302, 303}
    with app.app_context():
        assert CustomerUser.query.filter_by(email="dup@example.com").first() is None
        assert PendingSignup.query.filter_by(email="dup@example.com").count() == 1


def test_register_duplicate_verified_shows_error(client, app):
    with app.app_context():
        db.session.add(
            CustomerUser(
                email="dup@example.com",
                password_hash=generate_password_hash("secure-password-12", method="scrypt"),
                status="active",
                email_verified=True,
                nickname_completed=True,
            )
        )
        db.session.commit()

    again = client.post(
        "/auth/register",
        data={
            "email": "dup@example.com",
            "password": "secure-password-12",
            "confirm_password": "secure-password-12",
        },
    )
    assert again.status_code == 400
    assert b"already exists" in again.data


def test_nickname_guard(client, app):
    with app.app_context():
        user = CustomerUser(
            email="nick@example.com",
            password_hash="x",
            email_verified=True,
            nickname_completed=False,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    blocked = client.get("/dashboard", follow_redirects=False)
    assert blocked.status_code in {302, 303}
    assert "/auth/nickname" in blocked.headers["Location"]


def test_expired_code_rejected(app):
    with app.app_context():
        user = CustomerUser(
            email="expire@example.com",
            password_hash="x",
            email_verified=False,
        )
        db.session.add(user)
        db.session.flush()
        record = EmailVerification(
            user_id=user.id,
            purpose="registration",
            code_hash=hash_secret(f"{user.id}:registration:123456"),
            expires_at=utcnow() - timedelta(minutes=1),
            resend_available_at=utcnow(),
        )
        db.session.add(record)
        db.session.commit()
        with pytest.raises(auth_service.AuthError):
            auth_service.verify_code(user, "registration", "123456")


def test_owner_role_cannot_authenticate_on_customer(app):
    from werkzeug.security import generate_password_hash

    with app.app_context():
        user = CustomerUser(
            email="barongclassifier@gmail.com",
            password_hash=generate_password_hash("secure-password-12", method="scrypt"),
            full_name="Owner",
            role="owner",
            status="active",
            email_verified=True,
            nickname_completed=True,
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()

        with pytest.raises(auth_service.AuthError) as exc:
            auth_service.authenticate("barongclassifier@gmail.com", "secure-password-12")
        assert exc.value.status_code == 403
        assert "Owner" in str(exc.value)
