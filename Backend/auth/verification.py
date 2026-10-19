"""Six-digit email codes. Only hashes are stored."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

CODE_TTL = timedelta(hours=1)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=15)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def hash_value(secret: str, value: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def hashes_match(stored: str, presented: str) -> bool:
    return hmac.compare_digest(stored, presented)


@dataclass
class CodeRecord:
    user_id: str
    code_hash: str
    expires_at: datetime
    resend_available_at: datetime
    attempts: int = 0
    consumed_at: datetime | None = None
    locked_until: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)


class MemoryVerificationStore:
    """Same rules as private.issue_verification_code / consume_verification_code."""

    def __init__(self) -> None:
        self.codes: dict[str, list[CodeRecord]] = {}
        self.challenges: dict[str, tuple[str, datetime]] = {}

    def issue(self, user_id: str, code_hash: str, now: datetime | None = None) -> dict:
        now = now or utcnow()
        rows = self.codes.setdefault(user_id, [])
        latest = next((row for row in reversed(rows) if row.consumed_at is None), None)
        if latest and latest.locked_until and latest.locked_until > now:
            return {
                "ok": False,
                "error": "locked",
                "retry_after_seconds": int((latest.locked_until - now).total_seconds() + 0.999),
            }
        if (
            latest
            and latest.resend_available_at > now
            and latest.expires_at > now
        ):
            return {
                "ok": False,
                "error": "cooldown",
                "retry_after_seconds": int((latest.resend_available_at - now).total_seconds() + 0.999),
            }
        for row in rows:
            if row.consumed_at is None:
                row.consumed_at = now
        rows.append(
            CodeRecord(
                user_id=user_id,
                code_hash=code_hash,
                expires_at=now + CODE_TTL,
                resend_available_at=now + RESEND_COOLDOWN,
                created_at=now,
            )
        )
        return {
            "ok": True,
            "expires_at": (now + CODE_TTL).isoformat(),
            "resend_available_at": (now + RESEND_COOLDOWN).isoformat(),
        }

    def consume(self, user_id: str, code_hash: str, now: datetime | None = None) -> dict:
        now = now or utcnow()
        latest = next(
            (row for row in reversed(self.codes.get(user_id, [])) if row.consumed_at is None),
            None,
        )
        if latest is None:
            return {"ok": False, "error": "invalid"}
        if latest.locked_until and latest.locked_until > now:
            return {"ok": False, "error": "locked"}
        if latest.expires_at <= now:
            return {"ok": False, "error": "expired"}
        if latest.attempts >= MAX_ATTEMPTS:
            latest.locked_until = now + LOCK_DURATION
            return {"ok": False, "error": "locked"}
        if hashes_match(latest.code_hash, code_hash):
            latest.consumed_at = now
            self.challenges = {
                key: value for key, value in self.challenges.items() if value[0] != user_id
            }
            return {"ok": True}
        latest.attempts += 1
        if latest.attempts >= MAX_ATTEMPTS:
            latest.locked_until = now + LOCK_DURATION
            return {"ok": False, "error": "locked"}
        return {"ok": False, "error": "invalid"}

    def save_challenge(self, user_id: str, token_hash: str, now: datetime | None = None) -> None:
        now = now or utcnow()
        self.challenges = {
            key: value
            for key, value in self.challenges.items()
            if value[0] != user_id and value[1] > now
        }
        self.challenges[token_hash] = (user_id, now + CODE_TTL)

    def resend_wait_seconds(self, user_id: str, now: datetime | None = None) -> int:
        now = now or utcnow()
        latest = next(
            (row for row in reversed(self.codes.get(user_id, [])) if row.consumed_at is None),
            None,
        )
        if not latest or latest.resend_available_at <= now:
            return 0
        return int((latest.resend_available_at - now).total_seconds() + 0.999)

    def take_challenge(self, token_hash: str, now: datetime | None = None) -> str | None:
        now = now or utcnow()
        found = self.challenges.get(token_hash)
        if not found or found[1] <= now:
            return None
        return found[0]
