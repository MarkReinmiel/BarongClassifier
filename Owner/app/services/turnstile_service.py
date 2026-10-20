"""Cloudflare Turnstile server-side verification."""

from __future__ import annotations

import logging

import httpx
from flask import current_app, request

logger = logging.getLogger("owner.turnstile")

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class TurnstileError(Exception):
    def __init__(self, message: str = "Confirm that you are human."):
        super().__init__(message)


def verify_turnstile(token: str | None) -> None:
    cfg = current_app.config
    if not cfg.get("TURNSTILE_ENABLED"):
        return

    secret = cfg.get("TURNSTILE_SECRET_KEY") or ""
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

    if not data.get("success"):
        raise TurnstileError("Human verification failed. Try again.")
