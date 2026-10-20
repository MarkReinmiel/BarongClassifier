from __future__ import annotations

import io

from flask import current_app
from PIL import Image


ALLOWED = {".jpg", ".jpeg", ".png", ".webp"}


def prepare_image_bytes(file_storage) -> bytes:
    filename = (getattr(file_storage, "filename", "") or "").lower()
    suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    if suffix not in ALLOWED:
        raise ValueError("Use a JPG, PNG, or WEBP image.")

    raw = file_storage.read()
    max_bytes = current_app.config.get("MAX_CONTENT_LENGTH") or 10 * 1024 * 1024
    if len(raw) > max_bytes:
        raise ValueError("That image is too large.")

    image = Image.open(io.BytesIO(raw))
    image = image.convert("RGB")
    size = int(current_app.config.get("IMAGE_SIZE") or 224)
    # Keep original for the classify server; only validate it opens.
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()
