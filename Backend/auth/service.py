"""Authentication that keeps Supabase Auth as the credential store."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from auth.permissions import can_assign_role
from auth.verification import generate_code, hash_value
from config import settings
from services.email_service import EmailDeliveryError, send_verification_email

logger = logging.getLogger("barong.auth")

GENERIC_LOGIN = "Invalid email or password."
GENERIC_REGISTER = "If a new account can be created for that email, a verification code has been sent."


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


@dataclass
class UserRecord:
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    email_verified: bool
    must_change_password: bool


class AuthService:
    def __init__(self, store, directory, mailer=send_verification_email, require_config: bool = True) -> None:
        self.store = store
        self.directory = directory
        self.mailer = mailer
        self.require_config = require_config

    def register(self, full_name: str, email: str, password: str) -> dict:
        self._require_configured()
        email = email.strip().lower()
        if len(password) < 8:
            raise AuthError("Use at least 8 characters for the password.", 400)
        if settings.email_verification_enabled:
            self._require_privileged()
        created = self.directory.create_customer(email, password, full_name)
        if not created or not settings.email_verification_enabled:
            return {
                "message": "Account created. Sign in with that email and password."
                if created
                else GENERIC_REGISTER,
                "verification_required": False,
            }
        challenge = self._begin_verification(created)
        return {
            "message": GENERIC_REGISTER,
            "verification_required": True,
            "verification_token": challenge,
            "email_hint": mask_email(email),
            "resend_after_seconds": 60,
            "expires_in_seconds": 3600,
        }

    def login(self, email: str, password: str) -> dict:
        self._require_configured()
        email = email.strip().lower()
        signed_in = self.directory.authenticate(email, password)
        if not signed_in:
            raise AuthError(GENERIC_LOGIN, 401)
        profile = signed_in["profile"]
        if not profile.is_active:
            self.directory.revoke(signed_in)
            raise AuthError("This account is disabled.", 403)
        if settings.email_verification_enabled and not profile.email_verified:
            self.directory.revoke(signed_in)
            self._require_privileged()
            challenge = self._begin_verification(profile)
            return {
                "verification_required": True,
                "verification_token": challenge,
                "email_hint": mask_email(profile.email),
                "resend_after_seconds": 60,
                "expires_in_seconds": 3600,
            }
        self.directory.mark_login(profile.id)
        return {
            "verification_required": False,
            "role": profile.role,
            "must_change_password": profile.must_change_password,
            "session": signed_in["session"],
        }

    def verify(self, token: str, code: str) -> dict:
        self._require_configured()
        self._require_privileged()
        if not token or not code or len(code) != 6 or not code.isdigit():
            raise AuthError("Enter the six-digit code from your email.", 400)
        user_id = self.store.take_challenge(hash_value(settings.secret_key, token))
        if not user_id:
            raise AuthError("This verification session has expired. Sign in again.", 401)
        profile = self.directory.get_profile(user_id)
        result = self.store.consume(user_id, hash_value(settings.secret_key, f"{user_id}:{code}"))
        if not result.get("ok"):
            error = result.get("error")
            if error == "expired":
                raise AuthError("That code has expired. Request a new one.", 400)
            if error == "locked":
                raise AuthError("Too many attempts. Request a new code later.", 429)
            raise AuthError("That code is not valid.", 400)
        self.directory.mark_verified(user_id)
        refreshed = self.directory.get_profile(user_id)
        creator = getattr(self.directory, "create_session", None)
        session = creator(profile.email) if creator else None
        payload = {
            "verified": True,
            "role": refreshed.role,
            "must_change_password": refreshed.must_change_password,
        }
        if session:
            payload["session"] = session
        return payload

    def verification_status(self, token: str) -> dict:
        self._require_configured()
        user_id = self.store.take_challenge(hash_value(settings.secret_key, token))
        if not user_id:
            raise AuthError("This verification session has expired. Sign in again.", 401)
        wait = getattr(self.store, "resend_wait_seconds", lambda _user_id: 0)(user_id)
        return {
            "resend_after_seconds": int(wait or 0),
            "expires_in_seconds": settings.email_verification_expire_minutes * 60,
        }

    def resend(self, token: str) -> dict:
        self._require_configured()
        self._require_privileged()
        user_id = self.store.take_challenge(hash_value(settings.secret_key, token))
        if not user_id:
            raise AuthError("This verification session has expired. Sign in again.", 401)
        profile = self.directory.get_profile(user_id)
        self._send_code(profile)
        return {
            "message": "A new code was sent.",
            "resend_after_seconds": 60,
            "expires_in_seconds": 3600,
        }

    def current_user(self, access_token: str) -> UserRecord:
        profile = self.directory.profile_from_token(access_token)
        if not profile or not profile.is_active or not profile.email_verified:
            raise AuthError("Sign in again.", 401)
        return profile

    def change_password(self, access_token: str, new_password: str) -> None:
        if len(new_password) < 8:
            raise AuthError("Use at least 8 characters for the password.", 400)
        profile = self.current_user(access_token)
        self.directory.change_password(access_token, profile.id, new_password)

    def list_users(self, access_token: str) -> list[dict]:
        actor = self._admin(access_token)
        return self.directory.list_profiles(actor.id)

    def update_role(self, access_token: str, user_id: str, role: str) -> None:
        actor = self._admin(access_token)
        if not can_assign_role(actor.role, actor.id == user_id, role):
            raise AuthError("You cannot assign that role.", 403)
        self.directory.set_role(user_id, role)

    def update_status(self, access_token: str, user_id: str, is_active: bool) -> None:
        actor = self._admin(access_token)
        if actor.id == user_id:
            raise AuthError("You cannot change your own status.", 403)
        self.directory.set_active(user_id, is_active)

    def _admin(self, access_token: str) -> UserRecord:
        profile = self.current_user(access_token)
        if profile.role != "admin":
            raise AuthError("You do not have access to that action.", 403)
        return profile

    def _begin_verification(self, profile: UserRecord) -> str:
        self._send_code(profile)
        token = secrets.token_urlsafe(32)
        self.store.save_challenge(profile.id, hash_value(settings.secret_key, token))
        return token

    def _send_code(self, profile: UserRecord) -> None:
        code = generate_code()
        issued = self.store.issue(
            profile.id,
            hash_value(settings.secret_key, f"{profile.id}:{code}"),
        )
        if not issued.get("ok"):
            error = issued.get("error")
            if error == "cooldown":
                raise AuthError(
                    "Wait before requesting another code.",
                    429,
                    int(issued.get("retry_after_seconds") or settings.email_verification_resend_seconds),
                )
            raise AuthError("Verification is temporarily locked.", 429, int(issued.get("retry_after_seconds") or 0))
        try:
            self.mailer(profile.email, code)
        except EmailDeliveryError as error:
            logger.warning("Verification email was not delivered.")
            raise AuthError("The verification email could not be sent.", 502) from error

    def _require_configured(self) -> None:
        if not self.require_config:
            return
        if not settings.supabase_url or not settings.supabase_anon_key:
            logger.error("Supabase URL or anon key is missing.")
            raise AuthError("The authentication service is not configured.", 503)

    def _require_privileged(self) -> None:
        if not self.require_config:
            return
        missing = []
        database_ready = bool(settings.db_host and settings.db_password)
        if not settings.supabase_service_role_key and not database_ready:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
        if not settings.secret_key or settings.secret_key.startswith("replace_with"):
            missing.append("SECRET_KEY")
        missing.extend(settings.missing_smtp())
        if missing:
            logger.error("Privileged auth configuration is incomplete: %s", ", ".join(missing))
            raise AuthError("The authentication service is not configured.", 503)


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "your email"
    visible = local[:1]
    return f"{visible}***@{domain}"
