"""Load the local Keras textile classifier once per process."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

logger = logging.getLogger("owner.ml")

_LOCK = threading.Lock()
_MODEL = None
_CLASSES: list[str] | None = None
_IMAGE_SIZE: int | None = None
_MODEL_PATH: str | None = None

DISPLAY = {"cocoon": "Cocoon", "jusi": "Jusi", "pina": "Piña"}


def _resolve_path(path: str | Path, base: Path | None = None) -> Path:
    candidate = Path(path)
    if candidate.is_file():
        return candidate.resolve()
    if base is not None:
        rooted = (base / candidate).resolve()
        if rooted.is_file():
            return rooted
    return candidate


def _load_keras_model(model_path: Path):
    import tensorflow as tf

    try:
        return tf.keras.models.load_model(model_path)
    except (TypeError, ValueError) as error:
        if "renorm" not in str(error):
            raise
        return _load_without_renorm(model_path)


def _load_without_renorm(model_path: Path):
    """Load a model saved with Keras >= 3.14 on an older Keras 3 release."""
    import tensorflow as tf

    batch_norm = tf.keras.layers.BatchNormalization
    own_attribute = batch_norm.__dict__.get("from_config")
    inherited = batch_norm.from_config.__func__

    def from_config(cls, config):
        config = dict(config)
        if config.pop("renorm", False):
            raise ValueError("This model uses batch renormalization; install keras>=3.14.")
        config.pop("renorm_clipping", None)
        config.pop("renorm_momentum", None)
        return inherited(cls, config)

    batch_norm.from_config = classmethod(from_config)
    try:
        return tf.keras.models.load_model(model_path)
    finally:
        if own_attribute is None:
            del batch_norm.from_config
        else:
            batch_norm.from_config = own_attribute


def load_model(path: str, *, customer_root: Path | None = None):
    """Load (or reuse) the Keras model at path. Returns the model or None."""
    global _MODEL, _CLASSES, _IMAGE_SIZE, _MODEL_PATH

    resolved = _resolve_path(path, customer_root)
    labels_path = resolved.with_name("labels.json")
    if not resolved.is_file():
        logger.warning("Local model not found at %s", resolved)
        return None

    with _LOCK:
        if _MODEL is not None and _MODEL_PATH == str(resolved):
            return _MODEL

        if labels_path.is_file():
            labels = json.loads(labels_path.read_text(encoding="utf-8"))
            classes = list(labels.get("classes") or [])
            image_size = int(labels.get("image_size") or 224)
        else:
            classes = ["cocoon", "jusi", "pina"]
            image_size = 224

        try:
            model = _load_keras_model(resolved)
        except Exception:
            logger.exception("Failed to load Keras model from %s", resolved)
            return None

        _MODEL = model
        _CLASSES = classes
        _IMAGE_SIZE = image_size
        _MODEL_PATH = str(resolved)
        logger.info("Loaded local model %s (%s)", resolved.name, ", ".join(classes))
        return _MODEL


def get_model():
    return _MODEL


def get_classes() -> list[str]:
    return list(_CLASSES or [])


def get_image_size() -> int:
    return int(_IMAGE_SIZE or 224)


def display_name(class_key: str) -> str:
    key = (class_key or "").strip().lower()
    return DISPLAY.get(key, class_key)


def invalidate_cache() -> None:
    """Drop the in-memory production model so the next request reloads from disk."""
    global _MODEL, _CLASSES, _IMAGE_SIZE, _MODEL_PATH
    with _LOCK:
        _MODEL = None
        _CLASSES = None
        _IMAGE_SIZE = None
        _MODEL_PATH = None
        logger.info("Invalidated in-memory Keras model cache")
