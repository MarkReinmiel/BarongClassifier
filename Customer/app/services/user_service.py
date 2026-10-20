"""Safe user lookups and profile updates."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import CustomerUser, utcnow
from app.utils.validators import is_valid_email, nickname_errors, normalize_email


class UserServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def find_by_email(email: str) -> CustomerUser | None:
    return CustomerUser.query.filter_by(email=normalize_email(email)).first()


def find_by_id(user_id: str) -> CustomerUser | None:
    return CustomerUser.query.filter_by(id=user_id, is_active=True).first()


def mark_login(user: CustomerUser) -> None:
    user.last_login_at = utcnow()
    user.updated_at = utcnow()
    db.session.commit()


def save_nickname(user: CustomerUser, nickname: str) -> CustomerUser:
    errors = nickname_errors(nickname)
    if errors:
        raise UserServiceError(errors[0])
    user.nickname = nickname.strip()
    user.nickname_completed = True
    user.updated_at = utcnow()
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise UserServiceError("Could not save that nickname.") from error
    return user


def ensure_email_available(email: str) -> str:
    normalized = normalize_email(email)
    if not is_valid_email(normalized):
        raise UserServiceError("Enter a valid email address.")
    if find_by_email(normalized):
        raise UserServiceError("duplicate", status_code=409)
    return normalized
