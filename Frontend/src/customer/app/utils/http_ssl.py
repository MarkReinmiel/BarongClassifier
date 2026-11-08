"""HTTPS verify helpers for httpx on Windows (missing default CA PEM)."""

from __future__ import annotations

import os

from flask import current_app


def httpx_verify():
    """Return a CA bundle path, True, or False for httpx ``verify=``."""
    candidates: list[str] = []
    for env_key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        value = (os.environ.get(env_key) or "").strip()
        if value:
            candidates.append(value)
    try:
        import certifi

        candidates.append(certifi.where())
    except Exception:
        pass
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    if current_app.debug or (current_app.config.get("APP_ENV") or "").lower() in {
        "development",
        "local",
        "dev",
    }:
        return False
    return True
