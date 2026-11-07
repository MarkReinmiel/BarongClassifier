"""Filename helpers for standardized WebP uploads."""

from __future__ import annotations

from pathlib import PurePosixPath


def as_webp_filename(name: str | None, *, fallback: str = "upload") -> str:
    """Return a safe basename ending in ``.webp`` (history / Cloudinary / DB)."""
    raw = (name or "").strip() or fallback
    stem = PurePosixPath(raw.replace("\\", "/")).name
    if not stem or stem in {".", ".."}:
        stem = fallback
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    stem = stem.strip() or fallback
    return f"{stem}.webp"
