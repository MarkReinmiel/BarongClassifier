"""Configurable WebP conversion settings (env-aware, Flask-free)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WebPSettings:
    """Defaults match Phase 1 selected configuration."""

    quality: int = 90
    method: int = 6
    lossless: bool = False
    max_upload_bytes: int = 15 * 1024 * 1024
    max_width: int = 6000
    max_height: int = 6000
    # Used when flattening transparency to RGB.
    background_rgb: tuple[int, int, int] = (255, 255, 255)

    def __post_init__(self) -> None:
        if not 0 <= int(self.quality) <= 100:
            raise ValueError("quality must be between 0 and 100.")
        if not 0 <= int(self.method) <= 6:
            raise ValueError("method must be between 0 and 6.")
        if int(self.max_upload_bytes) < 1:
            raise ValueError("max_upload_bytes must be positive.")
        if int(self.max_width) < 1 or int(self.max_height) < 1:
            raise ValueError("max_width and max_height must be positive.")


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    return int(raw)


def settings_from_environ() -> WebPSettings:
    """Build settings from IMAGE_* environment variables when present."""
    defaults = WebPSettings()
    max_mb = os.environ.get("IMAGE_MAX_UPLOAD_MB")
    if max_mb and max_mb.strip():
        max_bytes = int(float(max_mb.strip()) * 1024 * 1024)
    else:
        max_bytes = defaults.max_upload_bytes
    return WebPSettings(
        quality=_env_int("IMAGE_WEBP_QUALITY", defaults.quality),
        method=_env_int("IMAGE_WEBP_METHOD", defaults.method),
        lossless=_env_bool("IMAGE_WEBP_LOSSLESS", defaults.lossless),
        max_upload_bytes=max_bytes,
        max_width=_env_int("IMAGE_MAX_WIDTH", defaults.max_width),
        max_height=_env_int("IMAGE_MAX_HEIGHT", defaults.max_height),
    )
