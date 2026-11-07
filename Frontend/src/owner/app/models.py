"""Reuse the existing customer.users table — Owner accounts share the same user rows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OwnerUser(db.Model):
    """Mapped to customer.users (same table Customer portal uses)."""

    __tablename__ = "users"
    __table_args__ = {"schema": "customer"}

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False, default="")
    role = db.Column(db.String(32), nullable=False, default="customer")
    status = db.Column(db.String(32), nullable=False, default="pending_verification")
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    nickname = db.Column(db.String(40))
    nickname_completed = db.Column(db.Boolean, nullable=False, default=False)
    phone = db.Column(db.String(40))
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
    role = db.Column(db.String(32), nullable=False, default="customer")
    status = db.Column(db.String(32), nullable=False, default="pending")
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    resend_available_at = db.Column(db.DateTime(timezone=True), nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    consumed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship("OwnerUser", backref=db.backref("verifications", lazy=True))
