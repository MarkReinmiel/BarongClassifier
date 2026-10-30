from __future__ import annotations

import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NICKNAME_RE = re.compile(r"^[A-Za-z0-9 _.\-]{2,40}$")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(normalize_email(email)))


def password_errors(password: str, confirm: str | None = None) -> list[str]:
    errors: list[str] = []
    if len(password or "") < 12:
        errors.append("Use at least 12 characters for the password.")
    if confirm is not None and password != confirm:
        errors.append("Passwords do not match.")
    return errors


def nickname_errors(nickname: str) -> list[str]:
    value = (nickname or "").strip()
    if not value:
        return ["Enter a nickname."]
    if not NICKNAME_RE.match(value):
        return ["Use 2–40 letters, numbers, spaces, dots, underscores, or hyphens."]
    return []
