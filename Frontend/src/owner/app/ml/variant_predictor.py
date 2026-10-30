"""Piña vs Piña Silk variant inference (separate from main 3-class model)."""

from __future__ import annotations

import io
import json
import logging
import threading
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger("owner.ml.variant")

_LOCK = threading.Lock()
_MODEL = None
_CLASSES: list[str] | None = None
_IMAGE_SIZE = 224
_THRESHOLD = 0.55
_MODEL_PATH: str | None = None
_VERSION = ""

DISPLAY = {"pina": "Ordinary Piña", "pina_silk": "Piña Silk"}


def _load_keras(path: Path):
    import tensorflow as tf

    try:
        return tf.keras.models.load_model(path)
    except (TypeError, ValueError) as error:
        if "renorm" not in str(error):
            raise
        from app.ml.model_loader import _load_without_renorm

        return _load_without_renorm(path)


def resolve_variant_paths(owner_root: Path, configured: str | None = None) -> tuple[Path | None, Path | None]:
    candidates = []
    if configured:
        candidates.append(Path(configured))
        candidates.append(owner_root / configured)
    candidates.extend(
        [
            owner_root / "models" / "barong_pina_variant.keras",
            owner_root.parent / "ml" / "models" / "variant" / "active" / "barong_pina_variant.keras",
        ]
    )
    for model_path in candidates:
        if model_path.is_file():
            labels = model_path.with_name("barong_pina_variant_labels.json")
            if not labels.is_file():
                labels = model_path.with_name("labels.json")
            return model_path, labels if labels.is_file() else None
    return None, None


def load_variant_model(owner_root: Path, configured: str | None = None):
    global _MODEL, _CLASSES, _IMAGE_SIZE, _THRESHOLD, _MODEL_PATH, _VERSION
    model_path, labels_path = resolve_variant_paths(owner_root, configured)
    if model_path is None:
        logger.info("Variant model not found; Piña variant stays undetermined.")
        return None
    with _LOCK:
        if _MODEL is not None and _MODEL_PATH == str(model_path):
            return _MODEL
        classes = ["pina", "pina_silk"]
        image_size = 224
        threshold = 0.55
        version = ""
        if labels_path and labels_path.is_file():
            data = json.loads(labels_path.read_text(encoding="utf-8"))
            classes = list(data.get("classes") or classes)
            image_size = int(data.get("image_size") or 224)
            threshold = float(data.get("acceptance_threshold") or 0.55)
            version = str(data.get("version") or "")
        try:
            model = _load_keras(model_path)
        except Exception:
            logger.exception("Failed to load variant model from %s", model_path)
            return None
        _MODEL = model
        _CLASSES = classes
        _IMAGE_SIZE = image_size
        _THRESHOLD = threshold
        _MODEL_PATH = str(model_path)
        _VERSION = version
        logger.info("Loaded variant model %s (%s)", model_path.name, ", ".join(classes))
        return _MODEL


def predict_variant(content: bytes) -> dict | None:
    if _MODEL is None:
        return None
    try:
        with Image.open(io.BytesIO(content)) as image:
            resized = image.convert("RGB").resize(
                (_IMAGE_SIZE, _IMAGE_SIZE), Image.Resampling.LANCZOS
            )
            batch = np.asarray(resized, dtype=np.uint8)[None, ...]
        with _LOCK:
            probs = _MODEL.predict(batch, verbose=0)[0]
        best = int(np.argmax(probs))
        conf = float(probs[best])
        key = (_CLASSES or ["pina", "pina_silk"])[best]
        if conf < _THRESHOLD:
            return {
                "variant": "undetermined",
                "variant_label": "Undetermined",
                "variant_confidence": conf,
                "status": "uncertain",
                "message": (
                    "Piña detected, but the Piña / Piña Silk variant could not be "
                    "determined reliably (low variant confidence)."
                ),
                "variant_model_version": _VERSION,
            }
        return {
            "variant": key,
            "variant_label": DISPLAY.get(key, key),
            "variant_confidence": conf,
            "status": "classified",
            "message": "",
            "variant_model_version": _VERSION,
        }
    except Exception:
        logger.exception("Variant prediction failed.")
        return None
