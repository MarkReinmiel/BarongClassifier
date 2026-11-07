"""Continue with Google via Supabase Auth → Flask customer.users session."""

from __future__ import annotations

import secrets
from urllib.parse import quote, urlencode

import httpx
from flask import current_app
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import CustomerUser, utcnow
from app.services.auth_service import AuthError
from app.services.directory_service import find_public_user_by_email
from app.utils.security import is_owner_role
from app.utils.validators import is_valid_email, normalize_email


def google_oauth_configured() -> bool:
    cfg = current_app.config
    return bool(
        cfg.get("GOOGLE_OAUTH_ENABLED")
        and cfg.get("SUPABASE_URL")
        and cfg.get("SUPABASE_PUBLISHABLE_KEY")
    )


def google_authorize_url(redirect_to: str) -> str:
    base = (current_app.config.get("SUPABASE_URL") or "").rstrip("/")
    if not base:
        raise AuthError("Google sign-in is not configured.", 503)
    query = urlencode(
        {
            "provider": "google",
            "redirect_to": redirect_to,
        },
        quote_via=quote,
    )
    return f"{base}/auth/v1/authorize?{query}"


def fetch_supabase_user(access_token: str) -> dict:
    """Validate the Supabase access token and return the Auth user payload."""
    base = (current_app.config.get("SUPABASE_URL") or "").rstrip("/")
    key = current_app.config.get("SUPABASE_PUBLISHABLE_KEY") or ""
    if not base or not key:
        raise AuthError("Google sign-in is not configured.", 503)
    if not access_token or len(access_token) < 20:
        raise AuthError("Google sign-in failed. Missing access token.", 400)

    try:
        response = httpx.get(
            f"{base}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "apikey": key,
            },
            timeout=12.0,
        )
    except httpx.HTTPError as exc:
        raise AuthError("Could not reach Google sign-in. Try again.", 503) from exc

    if response.status_code == 401:
        raise AuthError("Google sign-in expired. Please try again.", 401)
    if response.status_code >= 400:
        raise AuthError("Google sign-in could not be verified.", 400)

    payload = response.json() if response.content else {}
    if not isinstance(payload, dict):
        raise AuthError("Google sign-in returned an unexpected response.", 400)
    return payload


ACCOUNT_EXISTS_MSG = "An account with that email already exists. Please sign in instead."


def upsert_google_customer(access_token: str, *, intent: str = "login") -> CustomerUser:
    """Create or load a Customer portal user from a verified Google/Supabase session.

    intent=register → if the email already has a portal account, raise AuthError(409)
    so Create account can show the usual “already exists” message.
    intent=login → existing accounts are signed in normally.
    """
    intent = (intent or "login").strip().lower()
    if intent not in {"login", "register"}:
        intent = "login"

    auth_user = fetch_supabase_user(access_token)
    email = normalize_email(
        (auth_user.get("email") or "").strip()
        or ((auth_user.get("user_metadata") or {}).get("email") or "")
    )
    if not is_valid_email(email):
        raise AuthError("Google did not return a valid email for this account.", 400)

    meta = auth_user.get("user_metadata") or {}
    full_name = (
        (meta.get("full_name") or meta.get("name") or "").strip()
        or (auth_user.get("email") or "").split("@")[0]
    )[:120]

    directory = find_public_user_by_email(email)
    if directory:
        if directory.get("is_active") is False or directory.get("status") == "disabled":
            raise AuthError("This account is disabled.", 403)
        directory_role = (directory.get("role") or "").strip().lower()
        if is_owner_role(directory_role):
            raise AuthError(
                "This is an Owner account. Please sign in on the Owner portal, not the Customer site.",
                403,
            )

    user = CustomerUser.query.filter_by(email=email).first()
    if user:
        if is_owner_role(user.role):
            raise AuthError(
                "This is an Owner account. Please sign in on the Owner portal, not the Customer site.",
                403,
            )
        if not user.is_active or user.status == "disabled":
            raise AuthError("This account is disabled.", 403)
        if intent == "register":
            raise AuthError(ACCOUNT_EXISTS_MSG, 409)
        # Google already verified the mailbox.
        if not user.email_verified:
            user.email_verified = True
            if user.status == "pending_verification":
                user.status = "active"
            user.updated_at = utcnow()
            db.session.commit()
        return user

    # Email already reserved in the shared directory (password signup, etc.).
    if directory and intent == "register":
        raise AuthError(ACCOUNT_EXISTS_MSG, 409)

    # New Google customer — no password login unless they set one later.
    user = CustomerUser(
        email=email,
        password_hash=generate_password_hash(secrets.token_urlsafe(48), method="scrypt"),
        full_name=full_name,
        role="customer",
        status="active",
        email_verified=True,
        nickname_completed=False,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    return user
