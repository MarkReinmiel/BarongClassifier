"""Owner authentication and password-reset codes against customer.users."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import EmailVerification, OwnerUser, utcnow
from app.services.directory_service import find_public_user_by_email
from app.services.email_service import (
    EmailDeliveryError,
    send_password_changed_email,
    send_verification_email,
)
from app.utils.security import generate_code, hash_secret, hashes_match, is_owner_role
from app.utils.validators import is_valid_email, normalize_email, password_errors

MAX_ATTEMPTS = 5
LOCK_MINUTES = 15
PURPOSE_RESET = "password_reset"


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400, retry_after: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def authenticate_owner(email: str, password: str) -> OwnerUser:
    email = normalize_email(email)
    if not is_valid_email(email):
        raise AuthError("Enter a valid email address.")

    # Generic failure for missing / wrong credentials (do not leak existence).
    generic = AuthError("Invalid email or password.", 401)

    directory = find_public_user_by_email(email)
    user = OwnerUser.query.filter_by(email=email).first()
    if not user or not user.password_hash:
        raise generic
    if not check_password_hash(user.password_hash, password):
        raise generic
    if not user.is_active or user.status == "disabled":
        raise AuthError("This account is disabled.", 403)
    if directory and (directory.get("is_active") is False or directory.get("status") == "disabled"):
        raise AuthError("This account is disabled.", 403)

    role = (directory.get("role") if directory else None) or user.role
    if not is_owner_role(role):
        raise AuthError("This account is not authorized for the Owner Portal.", 403)

    return user


def request_password_reset(email: str) -> OwnerUser:
    """Require an existing Owner account with credentials before sending email."""
    email = normalize_email(email)
    if not is_valid_email(email):
        raise AuthError("Enter a valid email address.")

    user = OwnerUser.query.filter_by(email=email).first()
    if not user or not user.password_hash:
        raise AuthError(
            "No Owner account with credentials was found for that email.",
            404,
        )
    if not user.is_active or user.status == "disabled":
        raise AuthError("This account is disabled.", 403)
    if not is_owner_role(user.role):
        directory = find_public_user_by_email(email)
        role = (directory.get("role") if directory else None) or user.role
        if not is_owner_role(role):
            raise AuthError(
                "No Owner account with credentials was found for that email.",
                404,
            )

    issue_and_send_code(user, PURPOSE_RESET)
    return user


def issue_and_send_code(user: OwnerUser, purpose: str) -> dict:
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
        role=user.role or "owner",
        status="pending",
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


def resend_wait_seconds(user: OwnerUser, purpose: str) -> int:
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


def verify_code(user: OwnerUser, purpose: str, code: str) -> None:
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
    user.updated_at = now
    db.session.commit()


def reset_password(user: OwnerUser, password: str, confirm: str) -> None:
    for message in password_errors(password, confirm):
        raise AuthError(message)

    user.password_hash = generate_password_hash(password, method="scrypt")
    user.updated_at = utcnow()
    # Invalidate any remaining password-reset codes.
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
        # Password already changed; notify failure without rolling back.
        raise AuthError(
            "Password updated, but the confirmation email could not be sent.",
            502,
        )


def touch_login(user: OwnerUser) -> None:
    from flask import current_app

    user.last_login_at = utcnow()
    try:
        db.session.commit()
    except Exception:
        # public.users sync triggers can conflict; never fail the sign-in itself.
        current_app.logger.exception("Could not persist owner last_login_at.")
        try:
            db.session.rollback()
        except Exception:
            pass


def change_password(user: OwnerUser, current_password: str, new_password: str, confirm: str) -> None:
    if not check_password_hash(user.password_hash, current_password or ""):
        raise AuthError("Current password is incorrect.", 401)
    for message in password_errors(new_password, confirm):
        raise AuthError(message)
    user.password_hash = generate_password_hash(new_password, method="scrypt")
    user.updated_at = utcnow()
    db.session.commit()
    try:
        send_password_changed_email(user.email)
    except EmailDeliveryError:
        # Password already changed; confirmation email is best-effort.
        pass


def _ensure_owner_phone_column() -> None:
    """Add optional phone column once if older databases do not have it yet."""
    if current_app.config.get("TESTING"):
        return
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError

    try:
        db.session.execute(
            text("alter table customer.users add column if not exists phone varchar(40)")
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()


def update_owner_profile(user: OwnerUser, full_name: str, phone: str | None = None) -> OwnerUser:
    display = (full_name or "").strip()
    if not display:
        raise AuthError("Display name is required.")
    if len(display) > 120:
        raise AuthError("Display name must be 120 characters or fewer.")

    contact = (phone or "").strip()
    if len(contact) > 40:
        raise AuthError("Contact number must be 40 characters or fewer.")

    _ensure_owner_phone_column()
    user.full_name = display
    user.phone = contact or None
    user.updated_at = utcnow()

    if not current_app.config.get("TESTING"):
        from sqlalchemy import text
        from sqlalchemy.exc import SQLAlchemyError

        try:
            db.session.execute(
                text("select set_config('app.trusted_profile_write', '1', true)")
            )
            db.session.execute(
                text(
                    """
                    update public.users
                    set full_name = :full_name,
                        updated_at = now()
                    where id::text = :id
                       or lower(trim(email)) = :email
                    """
                ),
                {
                    "full_name": display,
                    "id": str(user.id),
                    "email": normalize_email(user.email),
                },
            )
        except SQLAlchemyError:
            db.session.rollback()
            raise AuthError("Profile could not be updated.", 503)

    db.session.commit()
    return user
