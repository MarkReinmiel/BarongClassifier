"""Supabase Auth and profile access. The service-role key stays on the server."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from supabase import create_client

from auth.service import UserRecord
from config import settings

logger = logging.getLogger("barong.auth")


def _profile_from_row(row: dict) -> UserRecord:
    return UserRecord(
        id=row["id"],
        email=(row.get("email") or "").lower(),
        full_name=row.get("full_name") or "",
        role=row.get("role") or "customer",
        is_active=bool(row.get("is_active", True)),
        email_verified=bool(row.get("email_verified", False)),
        must_change_password=bool(row.get("must_change_password", False)),
    )


class SupabaseDirectory:
    def __init__(self) -> None:
        self.admin = create_client(settings.supabase_url, settings.supabase_service_role_key)
        self.public = create_client(settings.supabase_url, settings.supabase_anon_key)

    def create_customer(self, email: str, password: str, full_name: str) -> UserRecord | None:
        try:
            created = self.admin.auth.admin.create_user(
                {
                    "email": email,
                    "password": password,
                    "email_confirm": False,
                    "user_metadata": {"full_name": full_name},
                    "app_metadata": {"role": "customer"},
                }
            )
        except Exception as error:
            message = str(error).lower()
            if "already" in message or "exists" in message or "duplicate" in message:
                return None
            logger.warning("Account creation failed.")
            raise
        user = created.user
        if not user:
            return None
        return self.get_profile(user.id)

    def authenticate(self, email: str, password: str) -> dict | None:
        try:
            result = self.public.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
        except Exception:
            return None
        if not result.session or not result.user:
            return None
        profile = self.get_profile(result.user.id)
        return {
            "profile": profile,
            "session": _session_payload(result.session),
            "access_token": result.session.access_token,
        }

    def revoke(self, signed_in: dict) -> None:
        try:
            self.admin.auth.admin.sign_out(signed_in["access_token"])
        except Exception:
            logger.warning("Could not revoke the temporary sign-in.")

    def get_profile(self, user_id: str) -> UserRecord:
        result = (
            self.admin.table("profiles")
            .select("id, email, full_name, role, is_active, email_verified, must_change_password")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return _profile_from_row(result.data)

    def mark_login(self, user_id: str) -> None:
        self.admin.table("profiles").update(
            {"last_login_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", user_id).execute()

    def mark_verified(self, user_id: str) -> None:
        return None

    def create_session(self, email: str) -> dict:
        link = self.admin.auth.admin.generate_link({"type": "magiclink", "email": email})
        token_hash = link.properties.hashed_token
        verified = self.public.auth.verify_otp({"token_hash": token_hash, "type": "email"})
        if not verified.session:
            raise RuntimeError("Session was not created.")
        return _session_payload(verified.session)

    def profile_from_token(self, access_token: str) -> UserRecord | None:
        try:
            user_response = self.public.auth.get_user(access_token)
        except Exception:
            return None
        user = user_response.user
        if not user:
            return None
        return self.get_profile(user.id)

    def change_password(self, access_token: str, user_id: str, new_password: str) -> None:
        self.admin.auth.admin.update_user_by_id(user_id, {"password": new_password})
        self.admin.table("profiles").update({"must_change_password": False}).eq("id", user_id).execute()

    def list_profiles(self, actor_id: str) -> list[dict]:
        result = (
            self.admin.table("profiles")
            .select("id, email, full_name, role, is_active, email_verified, created_at, last_login_at")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def set_role(self, user_id: str, role: str) -> None:
        self.admin.table("profiles").update({"role": role}).eq("id", user_id).execute()
        self.admin.auth.admin.update_user_by_id(user_id, {"app_metadata": {"role": role}})

    def set_active(self, user_id: str, is_active: bool) -> None:
        self.admin.table("profiles").update({"is_active": is_active}).eq("id", user_id).execute()


class SupabaseVerificationStore:
    def __init__(self, admin) -> None:
        self.admin = admin

    def issue(self, user_id: str, code_hash: str) -> dict:
        result = self.admin.rpc(
            "svc_issue_verification_code",
            {"p_user_id": user_id, "p_code_hash": code_hash},
        ).execute()
        return result.data

    def consume(self, user_id: str, code_hash: str) -> dict:
        result = self.admin.rpc(
            "svc_consume_verification_code",
            {"p_user_id": user_id, "p_code_hash": code_hash},
        ).execute()
        return result.data

    def save_challenge(self, user_id: str, token_hash: str) -> None:
        self.admin.rpc(
            "svc_save_challenge",
            {"p_user_id": user_id, "p_token_hash": token_hash},
        ).execute()

    def take_challenge(self, token_hash: str) -> str | None:
        result = self.admin.rpc(
            "svc_take_challenge",
            {"p_token_hash": token_hash},
        ).execute()
        return result.data

    def resend_wait_seconds(self, user_id: str) -> int:
        return 0


def _session_payload(session) -> dict:
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_in": session.expires_in,
        "token_type": session.token_type,
    }


class PublicDirectory:
    """Sign-in for accounts that are already verified, without the service-role key."""

    def __init__(self) -> None:
        self.public = create_client(settings.supabase_url, settings.supabase_anon_key)

    def create_customer(self, email: str, password: str, full_name: str) -> UserRecord | None:
        try:
            result = self.public.auth.sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {"data": {"full_name": full_name}},
                }
            )
        except Exception as error:
            message = str(error).lower()
            if "already" in message or "registered" in message or "exists" in message:
                return None
            logger.warning("Account creation failed.")
            raise
        user = result.user
        if not user or not user.id:
            return None
        identities = getattr(user, "identities", None)
        if identities is not None and len(identities) == 0:
            return None
        return UserRecord(
            id=str(user.id),
            email=email,
            full_name=full_name,
            role="customer",
            is_active=True,
            email_verified=not settings.email_verification_enabled,
            must_change_password=False,
        )

    def authenticate(self, email: str, password: str) -> dict | None:
        try:
            result = self.public.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
        except Exception:
            return None
        if not result.session or not result.user:
            return None
        profile_row = (
            self.public.table("profiles")
            .select("id, email, full_name, role, is_active, email_verified, must_change_password")
            .eq("id", result.user.id)
            .single()
            .execute()
        )
        return {
            "profile": _profile_from_row(profile_row.data),
            "session": _session_payload(result.session),
            "access_token": result.session.access_token,
        }

    def revoke(self, signed_in: dict) -> None:
        try:
            self.public.auth.sign_out()
        except Exception:
            logger.warning("Could not revoke the temporary sign-in.")

    def mark_login(self, user_id: str) -> None:
        return None

    def get_profile(self, user_id: str) -> UserRecord:
        from auth.postgres_verification import fetch_profile

        return fetch_profile(user_id)

    def mark_verified(self, user_id: str) -> None:
        from auth.postgres_verification import mark_profile_verified

        mark_profile_verified(user_id)


def build_service():
    from auth.postgres_verification import PostgresVerificationStore
    from auth.service import AuthService
    from auth.verification import MemoryVerificationStore

    if settings.supabase_service_role_key:
        directory = SupabaseDirectory()
    else:
        directory = PublicDirectory()

    if settings.db_host and settings.db_password:
        store = PostgresVerificationStore()
    elif settings.supabase_service_role_key:
        store = SupabaseVerificationStore(directory.admin)
    else:
        store = MemoryVerificationStore()
    return AuthService(store, directory)
