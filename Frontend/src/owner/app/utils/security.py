from __future__ import annotations

import hashlib
import hmac
import secrets
from functools import wraps

from flask import abort, current_app, make_response, redirect, request, session, url_for

from app.models import OwnerUser


def generate_code(length: int = 6) -> str:
    upper = 10**length
    return f"{secrets.randbelow(upper):0{length}d}"


def hash_secret(value: str) -> str:
    secret = current_app.config["SECRET_KEY"]
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def hashes_match(stored: str, presented: str) -> bool:
    return hmac.compare_digest(stored, presented)


def mask_email(email: str) -> str:
    local, _, domain = (email or "").partition("@")
    if not domain:
        return "your email"
    return f"{local[:1]}***@{domain}"


def current_user() -> OwnerUser | None:
    user_id = session.get("owner_user_id")
    if not user_id:
        return None
    try:
        return OwnerUser.query.filter_by(id=str(user_id), is_active=True).first()
    except RuntimeError as exc:
        # Dual-host: SQLAlchemy instance lost this Flask app — rebind and retry.
        if "not registered" not in str(exc).lower():
            current_app.logger.exception("Owner current_user() lookup failed")
            return None
        try:
            from app.extensions import db

            db.init_app(current_app._get_current_object())
            return OwnerUser.query.filter_by(id=str(user_id), is_active=True).first()
        except Exception:
            current_app.logger.exception("Owner current_user() rebind failed")
            return None
    except Exception:
        current_app.logger.exception("Owner current_user() lookup failed")
        return None


def is_owner_role(role: str | None) -> bool:
    allowed = current_app.config.get("OWNER_ROLES") or frozenset({"owner"})
    return (role or "").strip().lower() in allowed


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("auth.login", next=request.path))
        if not is_owner_role(user.role):
            session.clear()
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def no_store(response):
    response = make_response(response)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response
