"""Customer-schema tables. Isolated from Supabase Auth public.users (auth FK)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import deferred

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CustomerUser(db.Model):
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
    # Legacy whole-tour flag (kept in sync with tour_progress.main).
    tour_completed = db.Column(db.Boolean, nullable=False, default=False)
    # JSON: {"main":bool,"textile":bool,"history":bool,"profile":bool}
    # Deferred so login/dashboard still load if migration 0008 is not applied yet.
    tour_progress = deferred(db.Column(db.Text, nullable=True))
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
    role = db.Column(db.String(32), nullable=False, default="customer")
    status = db.Column(db.String(32), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_used_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("CustomerUser", backref=db.backref("devices", lazy=True))


class Classification(db.Model):
    """Portal history rows in public.classifications (visible in Supabase Table Editor)."""

    __tablename__ = "classifications"
    __table_args__ = {"schema": "public"}

    # DB columns are uuid; keep Python values as strings (as_uuid=False).
    id = db.Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = db.Column(UUID(as_uuid=False), nullable=False, index=True)
    file_name = db.Column(db.Text)
    predicted_label = db.Column(db.Text, nullable=False)
    display_name = db.Column(db.Text, nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    image_path = db.Column(db.Text)
    predicted_textile_type = db.Column(db.Text)
    confidence_score = db.Column(db.Float)
    image_reference = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    @property
    def image_name(self) -> str | None:
        return self.file_name
