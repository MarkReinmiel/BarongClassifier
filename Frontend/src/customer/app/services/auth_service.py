"""Registration, verification codes, trusted devices, nickname."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import CustomerUser, EmailVerification, TrustedDevice, utcnow
from app.services.directory_service import email_exists_in_users_table, find_public_user_by_email
from app.services.email_service import (
    EmailDeliveryError,
    send_password_changed_email,
    send_verification_email,
)
from app.utils.security import (
    generate_code,
    hash_secret,
    hashes_match,
    is_owner_role,
    new_device_token,
)
from app.utils.validators import (
    is_valid_email,
    nickname_errors,
    normalize_email,
    password_errors,
)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


MAX_ATTEMPTS = 5
LOCK_MINUTES = 15
PURPOSE_RESET = "password_reset"


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

    # Supabase public.users is the shared directory — block duplicates there.
    directory = find_public_user_by_email(email)
    if directory and is_owner_role(directory.get("role")):
        raise AuthError(
            "This email is registered as an Owner account. Use the Owner portal to sign in.",
            403,
        )
    if email_exists_in_users_table(email) or CustomerUser.query.filter_by(email=email).first():
        raise AuthError(
            "An account with that email already exists. Please sign in instead.",
            409,
        )

    skip_email = not current_app.config.get("EMAIL_VERIFICATION_ENABLED", True)
    user = CustomerUser(
        email=email,
        password_hash=generate_password_hash(password, method="scrypt"),
        full_name="",
        role="customer",
        status="active" if skip_email else "pending_verification",
        email_verified=bool(skip_email),
        nickname_completed=False,
    )
    db.session.add(user)
    db.session.flush()
    if not skip_email:
        issue_and_send_code(user, "registration")
    db.session.commit()
    return user


def authenticate(email: str, password: str) -> CustomerUser:
    email = normalize_email(email)
    if not is_valid_email(email):
        raise AuthError("Enter a valid email address.")

    # Require a row in Supabase public.users before password check.
    directory = find_public_user_by_email(email)
    if not directory:
        raise AuthError(
            "No account found for that email. Please create an account first.",
            404,
        )
    if directory.get("is_active") is False or directory.get("status") == "disabled":
        raise AuthError("This account is disabled.", 403)

    # Owner accounts must use the Owner portal only.
    directory_role = (directory.get("role") or "").strip().lower()
    if is_owner_role(directory_role):
        raise AuthError(
            "This is an Owner account. Please sign in on the Owner portal, not the Customer site.",
            403,
        )

    user = CustomerUser.query.filter_by(email=email).first()
    if not user:
        raise AuthError(
            "This email is in the users directory but has no Customer portal password. "
            "Please create a Customer account or use the main site sign-in.",
            404,
        )
    if is_owner_role(user.role):
        raise AuthError(
            "This is an Owner account. Please sign in on the Owner portal, not the Customer site.",
            403,
        )
    if not check_password_hash(user.password_hash, password):
        raise AuthError("Invalid email or password.", 401)
    if not user.is_active or user.status == "disabled":
        raise AuthError("This account is disabled.", 403)
    if not user.email_verified or user.status == "pending_verification":
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
        row.status = "consumed"

    ttl = timedelta(minutes=current_app.config["EMAIL_VERIFICATION_EXPIRE_MINUTES"])
    cooldown = timedelta(seconds=current_app.config["EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS"])
    length = current_app.config["EMAIL_VERIFICATION_CODE_LENGTH"]
    code = generate_code(length)
    record = EmailVerification(
        user_id=user.id,
        purpose=purpose,
        code_hash=hash_secret(f"{user.id}:{purpose}:{code}"),
        role=user.role or "customer",
        status="pending",
        expires_at=now + ttl,
        resend_available_at=now + cooldown,
    )
    db.session.add(record)
    try:
        send_verification_email(user.email, code, purpose)
    except EmailDeliveryError as error:
        db.session.rollback()
        # Use 400 (not 502): Cloudflare/Render often replace 5xx with a bare
        # "Internal Server Error" page and hide our flash message.
        raise AuthError(str(error), 400) from error
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
        record.status = "locked"
        db.session.commit()
        raise AuthError("Too many attempts. Try again later.", 429)

    expected = hash_secret(f"{user.id}:{purpose}:{code}")
    if not hashes_match(record.code_hash, expected):
        record.attempts += 1
        if record.attempts >= MAX_ATTEMPTS:
            record.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            record.status = "locked"
        db.session.commit()
        raise AuthError("That code is not valid.")

    record.consumed_at = now
    record.status = "consumed"
    if purpose == "registration":
        user.email_verified = True
        user.status = "active"
    user.updated_at = now
    db.session.commit()


def device_is_trusted(user: CustomerUser, raw_token: str | None) -> bool:
    if not raw_token:
        return False
    digest = hash_secret(raw_token)
    now = utcnow()
    device = TrustedDevice.query.filter_by(user_id=user.id, token_hash=digest).first()
    if not device or device.revoked_at or device.status == "revoked" or _aware(device.expires_at) <= now:
        if device and not device.revoked_at and _aware(device.expires_at) <= now and device.status != "expired":
            device.status = "expired"
            db.session.commit()
        return False
    device.last_used_at = now
    device.status = "active"
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
        role=user.role or "customer",
        status="active",
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
    user.full_name = user.nickname
    user.nickname_completed = True
    user.updated_at = utcnow()
    db.session.commit()


def request_password_reset(email: str) -> CustomerUser:
    """Require an existing Customer account before sending a reset code."""
    email = normalize_email(email)
    if not is_valid_email(email):
        raise AuthError("Enter a valid email address.")

    directory = find_public_user_by_email(email)
    if directory and is_owner_role(directory.get("role")):
        raise AuthError(
            "This email is registered as an Owner account. Use the Owner portal to reset.",
            403,
        )

    user = CustomerUser.query.filter_by(email=email).first()
    if not user or not user.password_hash:
        raise AuthError("No Customer account was found for that email.", 404)
    if is_owner_role(user.role):
        raise AuthError(
            "This email is registered as an Owner account. Use the Owner portal to reset.",
            403,
        )
    if not user.is_active or user.status == "disabled":
        raise AuthError("This account is disabled.", 403)
    if not user.email_verified or user.status == "pending_verification":
        raise AuthError("Verify your email before resetting your password.", 403)

    issue_and_send_code(user, PURPOSE_RESET)
    return user


def reset_password(user: CustomerUser, password: str, confirm: str) -> None:
    for message in password_errors(password, confirm):
        raise AuthError(message)

    user.password_hash = generate_password_hash(password, method="scrypt")
    user.updated_at = utcnow()
    now = utcnow()
    for row in EmailVerification.query.filter_by(
        user_id=user.id, purpose=PURPOSE_RESET, consumed_at=None
    ).all():
        row.consumed_at = now
        row.status = "consumed"
    db.session.commit()

    try:
        send_password_changed_email(user.email)
    except EmailDeliveryError:
        raise AuthError(
            "Password updated, but the confirmation email could not be sent.",
            400,
        )
