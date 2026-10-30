from __future__ import annotations

import math

import pytest
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import Classification, CustomerUser, TrustedDevice, utcnow
from app.services.classification_service import ClassificationError, validate_confidence
from app.services.history_service import get_owned, list_for_user
from datetime import timedelta


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


def test_health_endpoint(app):
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["database"] == "up"


def test_unique_email_constraint(app):
    with app.app_context():
        db.session.add(
            CustomerUser(email="unique@example.com", password_hash="hash-one")
        )
        db.session.commit()
        db.session.add(
            CustomerUser(email="unique@example.com", password_hash="hash-two")
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_classification_owned_by_user(app):
    with app.app_context():
        owner = CustomerUser(email="owner@example.com", password_hash="x", email_verified=True)
        other = CustomerUser(email="other@example.com", password_hash="x", email_verified=True)
        db.session.add_all([owner, other])
        db.session.flush()
        row = Classification(
            user_id=owner.id,
            predicted_label="Piña",
            display_name="Piña",
            confidence=0.91,
            file_name="a.jpg",
        )
        db.session.add(row)
        db.session.commit()

        history = list_for_user(owner)
        assert history["total"] == 1
        assert list_for_user(other)["total"] == 0
        assert get_owned(other, row.id) is None
        assert get_owned(owner, row.id) is not None


def test_confidence_validation():
    assert validate_confidence(0.5) == 0.5
    with pytest.raises(ClassificationError):
        validate_confidence(-0.1)
    with pytest.raises(ClassificationError):
        validate_confidence(1.2)
    with pytest.raises(ClassificationError):
        validate_confidence(math.nan)


def test_trusted_device_fields(app):
    with app.app_context():
        user = CustomerUser(email="device@example.com", password_hash="x")
        db.session.add(user)
        db.session.flush()
        device = TrustedDevice(
            user_id=user.id,
            token_hash="abc123",
            expires_at=utcnow() + timedelta(days=30),
        )
        db.session.add(device)
        db.session.commit()
        assert TrustedDevice.query.filter_by(user_id=user.id).count() == 1
