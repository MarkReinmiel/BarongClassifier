"""Upload classification images to Cloudinary; store returned secure_url in image_path."""

from __future__ import annotations

import logging
import re
from io import BytesIO

from flask import current_app

logger = logging.getLogger("owner.cloudinary")


def _cfg(name: str) -> str:
    return str(current_app.config.get(name) or "").strip().strip('"').strip("'")


def configured() -> bool:
    return bool(
        _cfg("CLOUDINARY_CLOUD_NAME")
        and _cfg("CLOUDINARY_API_KEY")
        and _cfg("CLOUDINARY_API_SECRET")
    )


def _safe_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "photo").strip()) or "photo"
    return stem[:80]


def upload_classification_image(
    *,
    content: bytes,
    filename: str,
    user_id: str,
    classification_id: str,
) -> str | None:
    """Upload image bytes. Returns Cloudinary secure_url, or None on skip/failure.

    Never invents a URL. Never logs API secrets.
    """
    if not content:
        logger.warning("cloudinary_skip reason=empty_image classification_id=%s", classification_id)
        return None
    if not configured():
        logger.warning(
            "cloudinary_skip reason=missing_env classification_id=%s "
            "(need CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET)",
            classification_id,
        )
        return None

    try:
        import cloudinary
        import cloudinary.uploader
    except ImportError:
        logger.error("cloudinary_skip reason=package_missing classification_id=%s", classification_id)
        return None

    cloud_name = _cfg("CLOUDINARY_CLOUD_NAME")
    api_key = _cfg("CLOUDINARY_API_KEY")
    api_secret = _cfg("CLOUDINARY_API_SECRET")

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )

    # Single Media Library folder: barong/classifications/
    # Phase 2 uploads are WebP bytes from prepare_image_bytes.
    public_id = f"barong/classifications/{classification_id}_{_safe_name(filename)}"
    if "." in public_id.rsplit("/", 1)[-1]:
        public_id = public_id.rsplit(".", 1)[0]

    try:
        result = cloudinary.uploader.upload(
            BytesIO(content),
            public_id=public_id,
            resource_type="image",
            overwrite=True,
            format="webp",
        )
    except Exception as error:
        msg = str(error)
        for secret in (api_secret, api_key):
            if secret and secret in msg:
                msg = msg.replace(secret, "[redacted]")
        logger.error(
            "cloudinary_upload_failed classification_id=%s public_id=%s error_type=%s error=%s",
            classification_id,
            public_id,
            type(error).__name__,
            msg[:300],
        )
        return None

    url = result.get("secure_url") or result.get("url")
    returned_id = result.get("public_id") or public_id
    if not url or not str(url).startswith("https://"):
        logger.error(
            "cloudinary_upload_failed classification_id=%s public_id=%s reason=no_secure_url",
            classification_id,
            returned_id,
        )
        return None

    logger.info(
        "cloudinary_upload_ok classification_id=%s public_id=%s bytes=%s",
        classification_id,
        returned_id,
        len(content),
    )
    return str(url)
