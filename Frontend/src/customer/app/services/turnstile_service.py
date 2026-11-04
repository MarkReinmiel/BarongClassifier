"""Cloudflare Turnstile server-side verification."""

from __future__ import annotations

import logging

import httpx
from flask import current_app, request

logger = logging.getLogger("customer.turnstile")

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class TurnstileError(Exception):
    def __init__(self, message: str = "Confirm that you are human."):
        super().__init__(message)


def request_hostname() -> str:
    return (request.host or "").split(":")[0].strip().lower()


def is_local_or_lan_host(hostname: str | None = None) -> bool:
    """True for localhost / private LAN IPs (mobile testing over Wi-Fi)."""
    host = (hostname or request_hostname()).strip().lower()
    if not host or host in {"localhost", "127.0.0.1", "::1"}:
        return True
    parts = host.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        a, b = int(parts[0]), int(parts[1])
        if a == 10 or a == 127:
            return True
        if a == 192 and b == 168:
            return True
        if a == 172 and 16 <= b <= 31:
            return True
    return False


def turnstile_active() -> bool:
    """Widget + verify when enabled and keys are configured."""
    if not current_app.config.get("TURNSTILE_ENABLED"):
        return False
    if not (current_app.config.get("TURNSTILE_SITE_KEY") or "").strip():
        return False
    return True


def verify_turnstile(token: str | None) -> None:
    if not turnstile_active():
        return

    secret = (current_app.config.get("TURNSTILE_SECRET_KEY") or "").strip()
    if not secret:
        logger.warning("Turnstile is enabled but TURNSTILE_SECRET_KEY is missing.")
        raise TurnstileError("Human verification is not configured.")

    response_token = (token or "").strip()
    if not response_token:
        raise TurnstileError("Complete the human verification checkbox.")

    payload = {
        "secret": secret,
        "response": response_token,
        "remoteip": request.headers.get("CF-Connecting-IP") or request.remote_addr or "",
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            result = client.post(SITEVERIFY_URL, data=payload)
            data = result.json()
    except Exception as error:
        logger.warning("Turnstile verification request failed.")
        raise TurnstileError("Human verification could not be checked. Try again.") from error

    if data.get("success"):
        return

    codes = data.get("error-codes") or []
    logger.warning("Turnstile rejected token error_codes=%s", codes)
    if "timeout-or-duplicate" in codes:
        raise TurnstileError("Human verification expired. Refresh and try again.")
    if "hostname-mismatch" in codes:
        raise TurnstileError(
            "Human verification hostname is not allowed. Add this site hostname "
            "in the Cloudflare Turnstile widget settings."
        )
    raise TurnstileError("Human verification failed. Try again.")
