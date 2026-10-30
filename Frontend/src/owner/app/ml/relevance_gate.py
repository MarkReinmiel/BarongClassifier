"""Textile relevance / OOD gate using the existing MobileNetV2 classifier.

Method (offline, no paid API, production CNN weights unchanged):
  1) Image-quality heuristics (brightness + Laplacian blur).
  2) Penultimate-feature distance to class centroids fitted on in-domain train data.
  3) Softmax max-probability + entropy as secondary soft signals (never sole decision).

Statuses (machine-readable, separate from display labels):
  classified | undefined_textile | uncertain | poor_image_quality

Display label for out-of-domain / unreliable domain membership:
  "Undefined Textile" — never remapped to Piña / Jusi / Cocoon.
"""

from __future__ import annotations

import io
import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger("owner.ml.relevance")

DISPLAY_UNDEFINED = "Undefined Textile"
STATUS_CLASSIFIED = "classified"
STATUS_UNDEFINED = "undefined_textile"
STATUS_UNCERTAIN = "uncertain"
STATUS_POOR = "poor_image_quality"

_SUPPORTED = frozenset({"cocoon", "jusi", "pina"})

_LOCK = threading.Lock()
_GATE_CACHE: dict[str, Any] = {"path": None, "config": None, "centroids": None, "feat_model": None}

# Conservative defaults used when relevance_gate.json is missing (experimental).
_DEFAULTS = {
    "experimental": True,
    "enabled": True,
    "image_size": 224,
    "classes": ["cocoon", "jusi", "pina"],
    "min_brightness": 0.08,
    "max_brightness": 0.95,
    "min_laplacian_var": 18.0,
    "max_centroid_distance": 0.55,
    "uncertain_centroid_distance": 0.42,
    "min_softmax_confidence": 0.45,
    "max_entropy": 0.95,
    "method": "hybrid_centroid_msp_quality",
}


@dataclass
class GateDecision:
    status: str
    display_label: str
    confidence: float
    message: str
    accept_textile: bool
    details: dict

    def as_result_fields(self) -> dict:
        return {
            "status": self.status,
            "label": self.display_label,
            "confidence": float(self.confidence),
            "main_class": (
                "undefined_textile"
                if self.status in {STATUS_UNDEFINED, STATUS_POOR}
                else ("uncertain" if self.status == STATUS_UNCERTAIN else "")
            ),
            "main_class_label": self.display_label,
            "variant": "not_applicable",
            "variant_label": "Not applicable",
            "main_confidence": float(self.confidence),
            "variant_confidence": None,
            "message": self.message,
            "gate": self.details,
        }


def gate_config_path(model_path: str | Path | None = None, app_root: Path | None = None) -> Path:
    if model_path:
        sibling = Path(model_path).with_name("relevance_gate.json")
        if sibling.is_file():
            return sibling
    if app_root is not None:
        candidate = app_root / "models" / "relevance_gate.json"
        if candidate.is_file():
            return candidate
    return (app_root or Path(".")) / "models" / "relevance_gate.json"


def load_gate_config(path: Path | None = None) -> dict:
    cfg = dict(_DEFAULTS)
    if path and path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except Exception:
            logger.exception("Failed to read relevance gate config %s", path)
    return cfg


def _rgb_from_bytes(content: bytes, image_size: int) -> np.ndarray:
    with Image.open(io.BytesIO(content)) as image:
        resized = image.convert("RGB").resize(
            (image_size, image_size), Image.Resampling.LANCZOS
        )
        return np.asarray(resized, dtype=np.uint8)


def assess_image_quality(rgb: np.ndarray, cfg: dict) -> tuple[str | None, dict]:
    """Return (status_or_None, metrics). status set only for poor_image_quality."""
    gray = rgb.astype(np.float32).mean(axis=2)
    brightness = float(gray.mean() / 255.0)
    # 3x3 Laplacian kernel variance (blur proxy).
    padded = np.pad(gray, 1, mode="edge")
    lap = (
        -4.0 * gray
        + padded[1:-1, :-2]
        + padded[1:-1, 2:]
        + padded[:-2, 1:-1]
        + padded[2:, 1:-1]
    )
    lap_var = float(lap.var())
    metrics = {
        "brightness": brightness,
        "laplacian_var": lap_var,
        "min_brightness": float(cfg["min_brightness"]),
        "max_brightness": float(cfg["max_brightness"]),
        "min_laplacian_var": float(cfg["min_laplacian_var"]),
    }
    if brightness < float(cfg["min_brightness"]) or brightness > float(cfg["max_brightness"]):
        return STATUS_POOR, metrics
    if lap_var < float(cfg["min_laplacian_var"]):
        return STATUS_POOR, metrics
    return None, metrics


def _l2_normalize(vectors: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.maximum(norms, eps)


def cosine_distances(features: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    """features (D,), centroids (C, D) → distances (C,) in [0, 2]."""
    f = _l2_normalize(features.reshape(1, -1))[0]
    c = _l2_normalize(centroids)
    sims = c @ f
    return 1.0 - sims


def softmax_entropy(probs: np.ndarray) -> float:
    p = np.clip(probs.astype(np.float64), 1e-12, 1.0)
    return float(-(p * np.log(p)).sum())


def _get_feature_model(model):
    cached = _GATE_CACHE.get("feat_model")
    if cached is not None and cached[0] is model:
        return cached[1]
    import tensorflow as tf

    dense = model.layers[-1]
    feat_model = tf.keras.Model(
        inputs=model.inputs,
        outputs=[dense.input, dense.output],
        name="barong_feat_probs",
    )
    _GATE_CACHE["feat_model"] = (model, feat_model)
    return feat_model


def _load_centroids(cfg: dict) -> np.ndarray | None:
    raw = cfg.get("centroids")
    classes = list(cfg.get("classes") or ["cocoon", "jusi", "pina"])
    if not isinstance(raw, dict) or not raw:
        return None
    rows = []
    for key in classes:
        vec = raw.get(key)
        if vec is None:
            return None
        rows.append(np.asarray(vec, dtype=np.float32))
    return np.stack(rows, axis=0)


def assess_relevance(
    content: bytes,
    *,
    model=None,
    model_path: str | Path | None = None,
    app_root: Path | None = None,
    enabled: bool | None = None,
) -> GateDecision | None:
    """Run the relevance gate.

    Returns None when the gate is disabled (caller should proceed with textile CNN only).
    """
    cfg_path = gate_config_path(model_path, app_root)
    cfg = load_gate_config(cfg_path if cfg_path.is_file() else None)
    if enabled is None:
        enabled = bool(cfg.get("enabled", True))
    if not enabled:
        return None

    image_size = int(cfg.get("image_size") or 224)
    rgb = _rgb_from_bytes(content, image_size)
    quality_status, quality = assess_image_quality(rgb, cfg)
    if quality_status == STATUS_POOR:
        return GateDecision(
            status=STATUS_POOR,
            display_label=DISPLAY_UNDEFINED,
            confidence=0.0,
            message=(
                "This photo looks too dark, bright, or blurry to classify reliably. "
                "Retake with clearer lighting and a steady close-up of the fabric."
            ),
            accept_textile=False,
            details={
                "method": cfg.get("method"),
                "experimental": bool(cfg.get("experimental", True)),
                "quality": quality,
                "reason": "poor_image_quality",
            },
        )

    details: dict[str, Any] = {
        "method": cfg.get("method"),
        "experimental": bool(cfg.get("experimental", True)),
        "quality": quality,
        "config_path": str(cfg_path) if cfg_path.is_file() else None,
    }

    probs = None
    min_dist = None
    max_prob = None
    entropy = None

    if model is not None:
        try:
            batch = rgb[None, ...]
            feat_model = _get_feature_model(model)
            with _LOCK:
                feats, probs = feat_model.predict(batch, verbose=0)
            feats = np.asarray(feats[0], dtype=np.float32)
            probs = np.asarray(probs[0], dtype=np.float32)
            max_prob = float(probs.max())
            entropy = softmax_entropy(probs)
            details["softmax_max"] = max_prob
            details["entropy"] = entropy
            details["predicted_index"] = int(np.argmax(probs))

            centroids = _load_centroids(cfg)
            if centroids is not None and centroids.shape[-1] == feats.shape[-1]:
                distances = cosine_distances(feats, centroids)
                min_dist = float(distances.min())
                details["centroid_distances"] = {
                    cls: float(d)
                    for cls, d in zip(cfg.get("classes") or [], distances)
                }
                details["min_centroid_distance"] = min_dist
            else:
                details["centroid_note"] = "centroids_unavailable"
        except Exception:
            logger.exception("Relevance feature scoring failed; falling back to quality-only.")
            details["feature_error"] = True

    # Decision policy
    max_dist = float(cfg["max_centroid_distance"])
    uncertain_dist = float(cfg["uncertain_centroid_distance"])
    min_conf = float(cfg["min_softmax_confidence"])
    max_ent = float(cfg["max_entropy"])

    if min_dist is not None and min_dist > max_dist:
        return GateDecision(
            status=STATUS_UNDEFINED,
            display_label=DISPLAY_UNDEFINED,
            confidence=max(0.0, 1.0 - min_dist),
            message=(
                "This image does not look like a supported Barong textile "
                "(Piña, Jusi, or Cocoon). Try a clear close-up of the fabric."
            ),
            accept_textile=False,
            details={**details, "reason": "far_from_textile_centroids"},
        )

    if min_dist is not None and min_dist > uncertain_dist:
        return GateDecision(
            status=STATUS_UNCERTAIN,
            display_label=DISPLAY_UNDEFINED,
            confidence=max_prob if max_prob is not None else max(0.0, 1.0 - min_dist),
            message=(
                "The system cannot reliably tell whether this is a supported textile. "
                "Retake a closer, well-lit fabric photo."
            ),
            accept_textile=False,
            details={**details, "reason": "borderline_centroid_distance"},
        )

    if max_prob is not None and (max_prob < min_conf or (entropy is not None and entropy > max_ent)):
        return GateDecision(
            status=STATUS_UNCERTAIN,
            display_label=DISPLAY_UNDEFINED,
            confidence=float(max_prob),
            message=(
                "The textile type could not be determined with enough confidence. "
                "Please capture another clear fabric image."
            ),
            accept_textile=False,
            details={**details, "reason": "low_softmax_or_high_entropy"},
        )

    # In-domain enough to run / accept textile prediction.
    conf = float(max_prob) if max_prob is not None else 1.0
    return GateDecision(
        status=STATUS_CLASSIFIED,
        display_label="",  # filled by textile classifier
        confidence=conf,
        message="",
        accept_textile=True,
        details={**details, "reason": "accepted"},
    )


def textile_key(label: str) -> str:
    raw = str(label or "").strip().lower().replace("ñ", "n")
    for key in _SUPPORTED:
        if key in raw:
            return key
    return ""
