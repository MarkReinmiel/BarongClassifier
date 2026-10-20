"""Optional local model loader. Prefer the classify server when available."""

from __future__ import annotations

_MODEL = None


def get_model():
    return _MODEL


def load_model(_path: str):
    global _MODEL
    _MODEL = None
    return _MODEL
