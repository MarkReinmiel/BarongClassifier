"""Load backend settings from the project .env file. Never log secret values."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")


def _first(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        cleaned = value.strip().strip('"').strip("'")
        if cleaned:
            return cleaned
    return ""


def _expand(value: str) -> str:
    if value == "${APP_NAME}":
        return _first("APP_NAME") or "BarongClassifier"
    return value


class Settings:
    app_name = _first("APP_NAME") or "BarongClassifier"
    secret_key = _first("SECRET_KEY")
    frontend_url = _first("FRONTEND_URL") or "http://127.0.0.1:5500"
    host = _first("HOST") or "127.0.0.1"
    port = int(_first("PORT") or "8000")
    cors_origins = [
        item.strip()
        for item in (_first("CORS_ORIGINS") or frontend_url).split(",")
        if item.strip()
    ]

    supabase_url = _first("NEXT_PUBLIC_SUPABASE_URL", "SUPABASE_URL")
    supabase_anon_key = _first(
        "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
        "SUPABASE_ANON_KEY",
    )
    supabase_service_role_key = _first("SUPABASE_SERVICE_ROLE_KEY")

    smtp_host = _first("SMTP_HOST", "MAIL_HOST")
    smtp_port = int(_first("SMTP_PORT", "MAIL_PORT") or "587")
    smtp_username = _first("SMTP_USERNAME", "MAIL_USERNAME")
    smtp_password = _first("SMTP_PASSWORD", "MAIL_PASSWORD")
    smtp_from_email = _first("SMTP_FROM_EMAIL", "MAIL_FROM_ADDRESS")
    smtp_from_name = _expand(_first("SMTP_FROM_NAME", "MAIL_FROM_NAME") or app_name)
    smtp_use_tls = _first("SMTP_USE_TLS", "MAIL_ENCRYPTION").lower() in {
        "1",
        "true",
        "tls",
        "starttls",
        "",
    }
    smtp_use_ssl = _first("SMTP_USE_SSL").lower() in {"1", "true", "ssl"}

    initial_admin_email = _first("INITIAL_ADMIN_EMAIL").lower()
    initial_admin_password = _first("INITIAL_ADMIN_PASSWORD")
    promote_existing_admin = _first("BOOTSTRAP_PROMOTE_EXISTING_ADMIN").lower() in {
        "1",
        "true",
        "yes",
    }
    email_verification_enabled = _first("EMAIL_VERIFICATION_ENABLED").lower() in {
        "1",
        "true",
        "yes",
    }
    email_verification_expire_minutes = int(
        _first("EMAIL_VERIFICATION_EXPIRE_MINUTES") or "60"
    )
    email_verification_resend_seconds = int(
        _first("EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS") or "60"
    )
    email_verification_code_length = int(_first("EMAIL_VERIFICATION_CODE_LENGTH") or "6")

    db_host = _first("DB_HOST")
    db_port = int(_first("DB_PORT") or "5432")
    db_name = _first("DB_DATABASE", "DB_NAME") or "postgres"
    db_user = _first("DB_USERNAME", "DB_USER")
    db_password = _first("DB_PASSWORD")
    db_sslmode = _first("DB_SSLMODE") or "require"

    def missing_smtp(self) -> list[str]:
        missing = []
        if not self.smtp_host:
            missing.append("SMTP_HOST")
        if not self.smtp_username:
            missing.append("SMTP_USERNAME")
        if not self.smtp_password:
            missing.append("SMTP_PASSWORD")
        if not self.smtp_from_email:
            missing.append("SMTP_FROM_EMAIL")
        return missing

    def missing_auth(self) -> list[str]:
        missing = []
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_anon_key:
            missing.append("SUPABASE_ANON_KEY")
        if not self.supabase_service_role_key and not (self.db_host and self.db_password):
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
        if not self.secret_key or self.secret_key.startswith("replace_with"):
            missing.append("SECRET_KEY")
        return missing


settings = Settings()
