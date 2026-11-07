from __future__ import annotations

import sys
from pathlib import Path

from flask import current_app


def _ensure_repo_root_on_path() -> Path:
    """Add monorepo root to sys.path so ``shared.image_processing`` imports work."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "shared" / "image_processing").is_dir():
            root = str(candidate)
            if root not in sys.path:
                sys.path.insert(0, root)
            return candidate
    raise RuntimeError("Could not locate BarongClassifier repo root for shared.image_processing.")


_ensure_repo_root_on_path()

from shared.image_processing import (  # noqa: E402
    ImageProcessingError,
    WebPSettings,
    convert_to_webp,
)


ALLOWED = {".jpg", ".jpeg", ".jpe", ".png", ".bmp", ".webp"}


def _webp_settings_from_app() -> WebPSettings:
    cfg = current_app.config
    max_bytes = int(
        cfg.get("IMAGE_MAX_UPLOAD_BYTES")
        or cfg.get("MAX_CONTENT_LENGTH")
        or (15 * 1024 * 1024)
    )
    return WebPSettings(
        quality=int(cfg.get("IMAGE_WEBP_QUALITY") or 90),
        method=int(cfg.get("IMAGE_WEBP_METHOD") or 6),
        lossless=bool(cfg.get("IMAGE_WEBP_LOSSLESS") or False),
        max_upload_bytes=max_bytes,
        max_width=int(cfg.get("IMAGE_MAX_WIDTH") or 6000),
        max_height=int(cfg.get("IMAGE_MAX_HEIGHT") or 6000),
    )


def prepare_image_bytes(file_storage) -> bytes:
    """Validate upload/camera bytes and return standardized WebP (Phase 2).

    Does not resize to 224×224; CNN predictors still resize at inference time.
    """
    filename = (getattr(file_storage, "filename", "") or "").lower()
    suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    if suffix and suffix not in ALLOWED:
        raise ValueError("Use a JPG, JPEG, JPE, PNG, BMP, or WEBP image.")

    raw = file_storage.read()
    max_bytes = int(
        current_app.config.get("IMAGE_MAX_UPLOAD_BYTES")
        or current_app.config.get("MAX_CONTENT_LENGTH")
        or (15 * 1024 * 1024)
    )
    if len(raw) > max_bytes:
        raise ValueError("That image is too large.")

    try:
        result = convert_to_webp(raw, settings=_webp_settings_from_app())
    except ImageProcessingError as error:
        raise ValueError(str(error)) from error
    return result.content
