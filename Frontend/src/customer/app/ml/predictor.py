"""Run local textile classification with the loaded Keras model."""

from __future__ import annotations

import io
import logging
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from app.ml.model_loader import (
    display_name,
    get_classes,
    get_image_size,
    get_model,
    load_model,
)

logger = logging.getLogger("customer.ml")
_PREDICT_LOCK = threading.Lock()


def ensure_model(model_path: str, customer_root: Path | None = None):
    model = get_model()
    if model is not None:
        return model
    return load_model(model_path, customer_root=customer_root)


def _batch_from_bytes(content: bytes, image_size: int) -> np.ndarray:
    with Image.open(io.BytesIO(content)) as image:
        resized = image.convert("RGB").resize(
            (image_size, image_size), Image.Resampling.LANCZOS
        )
        return np.asarray(resized, dtype=np.uint8)[None, ...]


def predict(
    image_input,
    *,
    model_path: str | None = None,
    customer_root: Path | None = None,
) -> tuple[str, float]:
    """Return (display_label, confidence) for image bytes or a uint8 array."""
    if model_path:
        model = ensure_model(model_path, customer_root=customer_root)
    else:
        model = get_model()
    if model is None:
        raise RuntimeError("Local CNN model is not loaded.")

    classes = get_classes() or ["cocoon", "jusi", "pina"]
    image_size = get_image_size()

    if isinstance(image_input, (bytes, bytearray)):
        batch = _batch_from_bytes(bytes(image_input), image_size)
    else:
        array = np.asarray(image_input)
        if array.ndim == 3:
            array = array[None, ...]
        batch = array

    with _PREDICT_LOCK:
        probabilities = model.predict(batch, verbose=0)[0]

    best = int(np.argmax(probabilities))
    key = classes[best] if best < len(classes) else str(best)
    return display_name(key), float(probabilities[best])
