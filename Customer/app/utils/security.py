from __future__ import annotations

import hashlib
import hmac
import secrets
from functools import wraps

from flask import abort, current_app, redirect, request, session, url_for

from app.models import CustomerUser


def generate_code(length: int = 6) -> str:
    upper = 10**length
    return f"{secrets.randbelow(upper):0{length}d}"


def hash_secret(value: str) -> str:
    secret = current_app.config["SECRET_KEY"]
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def hashes_match(stored: str, presented: str) -> bool:
    return hmac.compare_digest(stored, presented)


def new_device_token() -> str:
    return secrets.token_urlsafe(32)


def mask_email(email: str) -> str:
    local, _, domain = (email or "").partition("@")
    if not domain:
        return "your email"
    return f"{local[:1]}***@{domain}"


def current_user() -> CustomerUser | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return CustomerUser.query.filter_by(id=user_id, is_active=True).first()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("auth.login", next=request.path))
        if not user.email_verified:
            session.clear()
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def nickname_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("auth.login", next=request.path))
        if not user.email_verified:
            session.clear()
            return redirect(url_for("auth.login"))
        if not user.nickname_completed:
            return redirect(url_for("auth.nickname_setup"))
        return view(*args, **kwargs)

    return wrapped


def no_store(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def client_label() -> str:
    ua = (request.user_agent.string or "browser")[:100]
    return ua
