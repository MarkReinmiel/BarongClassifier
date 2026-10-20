from __future__ import annotations

import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


def password_strength(password: str) -> str:
    length = len(password or "")
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if length < 12 or classes < 2:
        return "weak"
    if length >= 14 and classes >= 3:
        return "strong"
    return "medium"
