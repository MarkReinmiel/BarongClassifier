"""Customer-schema tables. Isolated from Supabase public.profiles."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CustomerUser(db.Model):
    __tablename__ = "users"
    __table_args__ = {"schema": "customer"}

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    nickname = db.Column(db.String(40))
    nickname_completed = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    last_login_at = db.Column(db.DateTime(timezone=True))


class EmailVerification(db.Model):
    __tablename__ = "email_verifications"
    __table_args__ = {"schema": "customer"}

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("customer.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose = db.Column(db.String(32), nullable=False)
    code_hash = db.Column(db.String(128), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    resend_available_at = db.Column(db.DateTime(timezone=True), nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    consumed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship("CustomerUser", backref=db.backref("verifications", lazy=True))


class TrustedDevice(db.Model):
    __tablename__ = "trusted_devices"
    __table_args__ = {"schema": "customer"}

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("customer.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = db.Column(db.String(128), nullable=False, unique=True)
    label = db.Column(db.String(120))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_used_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("CustomerUser", backref=db.backref("devices", lazy=True))


class Classification(db.Model):
    __tablename__ = "classifications"
    __table_args__ = {"schema": "customer"}

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("customer.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    predicted_label = db.Column(db.String(64), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    image_name = db.Column(db.String(255))
    image_path = db.Column(db.String(512))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship("CustomerUser", backref=db.backref("classifications", lazy=True))
