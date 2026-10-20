"""Registration, verification codes, trusted devices, nickname."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import CustomerUser, EmailVerification, TrustedDevice, utcnow


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
from app.services.email_service import EmailDeliveryError, send_verification_email
from app.utils.security import generate_code, hash_secret, hashes_match, new_device_token
from app.utils.validators import (
    is_valid_email,
    nickname_errors,
    normalize_email,
    password_errors,
)

MAX_ATTEMPTS = 5
LOCK_MINUTES = 15


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400, retry_after: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def register_user(email: str, password: str, confirm: str) -> CustomerUser:
    email = normalize_email(email)
    if not is_valid_email(email):
        raise AuthError("Enter a valid email address.")
    for message in password_errors(password, confirm):
        raise AuthError(message)

    if CustomerUser.query.filter_by(email=email).first():
        raise AuthError("duplicate")

    user = CustomerUser(
        email=email,
        password_hash=generate_password_hash(password, method="scrypt"),
        email_verified=False,
        nickname_completed=False,
    )
    db.session.add(user)
    db.session.flush()
    issue_and_send_code(user, "registration")
    db.session.commit()
    return user


def authenticate(email: str, password: str) -> CustomerUser:
    email = normalize_email(email)
    user = CustomerUser.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        raise AuthError("Invalid email or password.", 401)
    if not user.is_active:
        raise AuthError("This account is disabled.", 403)
    if not user.email_verified:
        raise AuthError("Verify your email before signing in.", 403)
    return user


def issue_and_send_code(user: CustomerUser, purpose: str) -> dict:
    now = utcnow()
    latest = (
        EmailVerification.query.filter_by(user_id=user.id, purpose=purpose, consumed_at=None)
        .order_by(EmailVerification.created_at.desc())
        .first()
    )
    if latest and _aware(latest.locked_until) and _aware(latest.locked_until) > now:
        wait = int((_aware(latest.locked_until) - now).total_seconds() + 0.999)
        raise AuthError("Too many attempts. Try again later.", 429, wait)
    if (
        latest
        and _aware(latest.resend_available_at) > now
        and _aware(latest.expires_at) > now
    ):
        wait = int((_aware(latest.resend_available_at) - now).total_seconds() + 0.999)
        raise AuthError("Wait before requesting another code.", 429, wait)

    for row in EmailVerification.query.filter_by(
        user_id=user.id, purpose=purpose, consumed_at=None
    ).all():
        row.consumed_at = now

    ttl = timedelta(minutes=current_app.config["EMAIL_VERIFICATION_EXPIRE_MINUTES"])
    cooldown = timedelta(seconds=current_app.config["EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS"])
    length = current_app.config["EMAIL_VERIFICATION_CODE_LENGTH"]
    code = generate_code(length)
    record = EmailVerification(
        user_id=user.id,
        purpose=purpose,
        code_hash=hash_secret(f"{user.id}:{purpose}:{code}"),
        expires_at=now + ttl,
        resend_available_at=now + cooldown,
    )
    db.session.add(record)
    try:
        send_verification_email(user.email, code, purpose)
    except EmailDeliveryError as error:
        db.session.rollback()
        raise AuthError(str(error), 502) from error
    db.session.commit()
    return {
        "resend_after_seconds": int(cooldown.total_seconds()),
        "expires_in_seconds": int(ttl.total_seconds()),
        "resend_available_at": record.resend_available_at.isoformat(),
    }


def resend_wait_seconds(user: CustomerUser, purpose: str) -> int:
    now = utcnow()
    latest = (
        EmailVerification.query.filter_by(user_id=user.id, purpose=purpose, consumed_at=None)
        .order_by(EmailVerification.created_at.desc())
        .first()
    )
    available = _aware(latest.resend_available_at) if latest else None
    if not available or available <= now:
        return 0
    return int((available - now).total_seconds() + 0.999)


def verify_code(user: CustomerUser, purpose: str, code: str) -> None:
    code = (code or "").strip()
    length = current_app.config["EMAIL_VERIFICATION_CODE_LENGTH"]
    if len(code) != length or not code.isdigit():
        raise AuthError(f"Enter the {length}-digit code from your email.")

    now = utcnow()
    record = (
        EmailVerification.query.filter_by(user_id=user.id, purpose=purpose, consumed_at=None)
        .order_by(EmailVerification.created_at.desc())
        .first()
    )
    if not record:
        raise AuthError("That code is not valid.")
    if _aware(record.locked_until) and _aware(record.locked_until) > now:
        raise AuthError("Too many attempts. Try again later.", 429)
    if _aware(record.expires_at) <= now:
        raise AuthError("That code has expired. Request a new one.")
    if record.attempts >= MAX_ATTEMPTS:
        record.locked_until = now + timedelta(minutes=LOCK_MINUTES)
        db.session.commit()
        raise AuthError("Too many attempts. Try again later.", 429)

    expected = hash_secret(f"{user.id}:{purpose}:{code}")
    if not hashes_match(record.code_hash, expected):
        record.attempts += 1
        if record.attempts >= MAX_ATTEMPTS:
            record.locked_until = now + timedelta(minutes=LOCK_MINUTES)
        db.session.commit()
        raise AuthError("That code is not valid.")

    record.consumed_at = now
    if purpose == "registration":
        user.email_verified = True
    user.updated_at = now
    db.session.commit()


def device_is_trusted(user: CustomerUser, raw_token: str | None) -> bool:
    if not raw_token:
        return False
    digest = hash_secret(raw_token)
    now = utcnow()
    device = TrustedDevice.query.filter_by(user_id=user.id, token_hash=digest).first()
    if not device or device.revoked_at or _aware(device.expires_at) <= now:
        return False
    device.last_used_at = now
    db.session.commit()
    return True


def trust_device(user: CustomerUser, label: str | None = None) -> str:
    raw = new_device_token()
    days = current_app.config["DEVICE_TRUST_DAYS"]
    now = utcnow()
    device = TrustedDevice(
        user_id=user.id,
        token_hash=hash_secret(raw),
        label=(label or "")[:120] or None,
        expires_at=now + timedelta(days=days),
    )
    db.session.add(device)
    db.session.commit()
    return raw


def save_nickname(user: CustomerUser, nickname: str) -> None:
    errors = nickname_errors(nickname)
    if errors:
        raise AuthError(errors[0])
    user.nickname = nickname.strip()
    user.nickname_completed = True
    user.updated_at = utcnow()
    db.session.commit()
