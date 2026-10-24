"""Customer Flask settings from .env. Never log secret values."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        cleaned = value.strip().strip('"').strip("'")
        if cleaned:
            return cleaned
    return default


def _build_database_uri() -> str:
    database_url = _first("DATABASE_URL", "SQLALCHEMY_DATABASE_URI")
    if database_url:
        if database_url.startswith("postgres://"):
            return "postgresql+psycopg://" + database_url[len("postgres://") :]
        if database_url.startswith("postgresql://"):
            return "postgresql+psycopg://" + database_url[len("postgresql://") :]
        return database_url

    host = _first("DB_HOST")
    port = _first("DB_PORT", default="5432")
    name = _first("DB_DATABASE", "DB_NAME", default="postgres")
    user = _first("DB_USERNAME", "DB_USER")
    password = _first("DB_PASSWORD")
    sslmode = _first("DB_SSLMODE", default="require")
    if host and user and password:
        return (
            f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}"
            f"@{host}:{port}/{name}?sslmode={sslmode}"
        )
    return ""


class Config:
    APP_NAME = _first("APP_NAME", default="BarongClassifier")
    APP_ENV = _first("APP_ENV", default="development")
    SECRET_KEY = _first("SECRET_KEY") or "dev-only-change-me"
    DEBUG = _first("DEBUG", "FLASK_DEBUG").lower() in {"1", "true", "yes"}
    # Reload Jinja templates even if flask run was started without --debug
    TEMPLATES_AUTO_RELOAD = True

    DB_HOST = _first("DB_HOST")
    DB_PORT = _first("DB_PORT", default="5432")
    DB_NAME = _first("DB_DATABASE", "DB_NAME", default="postgres")
    DB_USER = _first("DB_USERNAME", "DB_USER")
    DB_PASSWORD = _first("DB_PASSWORD")
    DB_SSLMODE = _first("DB_SSLMODE", default="require")
    DB_POOL_MODE = _first("DB_POOL_MODE", default="session")
    SUPABASE_URL = _first("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL")
    SUPABASE_PUBLISHABLE_KEY = _first(
        "SUPABASE_PUBLISHABLE_KEY",
        "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    )

    SQLALCHEMY_DATABASE_URI = _build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    WTF_CSRF_TIME_LIMIT = None
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _first("SESSION_COOKIE_SECURE").lower() in {"1", "true", "yes"}
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = int(_first("ACCESS_TOKEN_EXPIRE_MINUTES", default="30")) * 60

    MAIL_HOST = _first("MAIL_HOST", "SMTP_HOST", "MAIL_SERVER", default="smtp.gmail.com")
    MAIL_PORT = int(_first("MAIL_PORT", "SMTP_PORT", default="587"))
    MAIL_USERNAME = _first("MAIL_USERNAME", "SMTP_USERNAME")
    MAIL_PASSWORD = _first("MAIL_PASSWORD", "SMTP_PASSWORD")
    MAIL_FROM_ADDRESS = _first(
        "MAIL_FROM_ADDRESS",
        "SMTP_FROM_EMAIL",
        "MAIL_DEFAULT_SENDER",
        default=MAIL_USERNAME,
    )
    MAIL_FROM_NAME = _first("MAIL_FROM_NAME", "SMTP_FROM_NAME", default=APP_NAME)
    MAIL_USE_TLS = _first("MAIL_ENCRYPTION", "SMTP_USE_TLS", "MAIL_USE_TLS", default="tls").lower() in {
        "1",
        "true",
        "tls",
        "starttls",
        "",
    }
    MAIL_USE_SSL = _first("SMTP_USE_SSL", "MAIL_USE_SSL").lower() in {"1", "true", "ssl"}

    EMAIL_VERIFICATION_ENABLED = _first("EMAIL_VERIFICATION_ENABLED", default="true").lower() in {
        "1",
        "true",
        "yes",
    }
    EMAIL_VERIFICATION_EXPIRE_MINUTES = int(
        _first("EMAIL_VERIFICATION_EXPIRE_MINUTES", default="1440")
    )
    EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS = int(
        _first("EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS", default="60")
    )
    EMAIL_VERIFICATION_CODE_LENGTH = int(_first("EMAIL_VERIFICATION_CODE_LENGTH", default="6"))
    DEVICE_TRUST_DAYS = int(_first("DEVICE_TRUST_DAYS", default="30"))
    DEVICE_COOKIE_NAME = "barong_device"
    BASE_URL = _first("BASE_URL", "CUSTOMER_URL", default="http://127.0.0.1:5000")

    MAX_CONTENT_LENGTH = int(float(_first("MAX_UPLOAD_SIZE_MB", default="10")) * 1024 * 1024)
    MODEL_PATH = _first("MODEL_PATH", default="models/barong_model.keras")
    VARIANT_MODEL_PATH = _first("VARIANT_MODEL_PATH", default="models/barong_pina_variant.keras")
    # Empty by default so Customer uses the local Keras model under models/.
    CLASSIFY_SERVER_URL = _first("CLASSIFY_SERVER_URL", default="")
    IMAGE_SIZE = int(_first("IMAGE_SIZE", default="224"))
    CLOUDINARY_CLOUD_NAME = _first("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = _first("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = _first("CLOUDINARY_API_SECRET")
    CLASS_NAMES = [
        item.strip()
        for item in _first("CLASS_NAMES", default="cocoon,jusi,pina").split(",")
        if item.strip()
    ]


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key-for-customer-auth"
    MAIL_USERNAME = "test@example.com"
    MAIL_PASSWORD = "x"
    MAIL_FROM_ADDRESS = "test@example.com"
    MAIL_HOST = "localhost"
