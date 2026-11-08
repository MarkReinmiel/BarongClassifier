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
from app.utils.http_ssl import httpx_verify
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
            verify=httpx_verify(),
        )
    except FileNotFoundError as exc:
        raise AuthError(
            "Google sign-in cannot verify HTTPS on this computer (missing SSL certificates).",
            503,
        ) from exc
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


def _is_explicitly_disabled(*, is_active, status: str | None) -> bool:
    """Match Owner manage-users: only block when clearly deactivated (null is_active = active)."""
    if is_active is False:
        return True
    return (status or "").strip().lower() == "disabled"


def upsert_google_customer(access_token: str, *, intent: str = "login") -> CustomerUser:
    """Create or load a Customer portal user from a verified Google/Supabase session.

    Existing portal accounts are always signed in (login or register entry point).
    New Google emails create a customer account and continue into onboarding.
    ``intent`` is kept for callers/logging only — it no longer blocks existing users.
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
    user = CustomerUser.query.filter_by(email=email).first()

    # Prefer the customer portal row for Customer Google login; fall back to directory.
    role = (user.role if user else None) or ((directory or {}).get("role") if directory else None)
    if is_owner_role(role):
        raise AuthError(
            "This is an Owner account. Please sign in on the Owner portal, not the Customer site.",
            403,
        )

    portal_disabled = bool(
        user
        and _is_explicitly_disabled(is_active=user.is_active, status=user.status)
    )
    directory_disabled = bool(
        directory
        and _is_explicitly_disabled(
            is_active=directory.get("is_active"),
            status=directory.get("status"),
        )
    )
    # If either side shows active, allow sign-in and heal the stale disabled flag.
    if user and portal_disabled and not directory_disabled:
        user.is_active = True
        user.status = "active"
        user.updated_at = utcnow()
        db.session.commit()
        portal_disabled = False
    if portal_disabled or (directory_disabled and not user):
        raise AuthError("This account is disabled.", 403)

    if user:
        # Existing account → sign in (regardless of login vs register entry point).
        if not user.email_verified:
            user.email_verified = True
            if user.status == "pending_verification":
                user.status = "active"
            user.updated_at = utcnow()
            db.session.commit()
        elif user.status == "pending_verification":
            user.status = "active"
            user.updated_at = utcnow()
            db.session.commit()
        return user

    # No portal account yet → create one from the verified Google profile.
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
