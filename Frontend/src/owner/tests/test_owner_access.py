from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import OwnerUser


@pytest.fixture()
def app():
    application = create_app(TestConfig)
    for table in db.metadata.tables.values():
        table.schema = None
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def test_logout_clears_session(client, app):
    with app.app_context():
        user = OwnerUser(
            email="owner@example.com",
            password_hash=generate_password_hash("secure-password-12", method="scrypt"),
            role="owner",
            status="active",
            email_verified=True,
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client.post("/login", data={"email": "owner@example.com", "password": "secure-password-12"})
    with client.session_transaction() as sess:
        assert sess.get("owner_user_id") == user_id

    response = client.post("/logout", follow_redirects=False)
    assert response.status_code in {302, 303}
    with client.session_transaction() as sess:
        assert sess.get("owner_user_id") is None


def test_non_owner_session_blocked_from_dashboard(client, app):
    with app.app_context():
        user = OwnerUser(
            email="cust@example.com",
            password_hash=generate_password_hash("secure-password-12", method="scrypt"),
            role="customer",
            status="active",
            email_verified=True,
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess["owner_user_id"] = user_id

    response = client.get("/dashboard")
    assert response.status_code == 403
