"""Errors raised by shared image processing."""

from __future__ import annotations


class ImageProcessingError(ValueError):
    """Invalid, unsupported, or oversized image input."""
