from __future__ import annotations

import json
import logging
from pathlib import Path

from app.models import Classification, CustomerUser

logger = logging.getLogger("customer.stats")
CUSTOMER_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = CUSTOMER_ROOT / "models"
REPO_ROOT = CUSTOMER_ROOT.parents[2]
BACKEND_METRICS = (
    REPO_ROOT / "Backend" / "machine learning" / "artifacts" / "metrics.json"
)


def _load_metrics() -> dict:
    for path in (MODELS_DIR / "metrics.json", BACKEND_METRICS):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            logger.exception("Could not read metrics from %s", path)
    return {}


def _load_class_count() -> int:
    labels_path = MODELS_DIR / "labels.json"
    if labels_path.is_file():
        try:
            data = json.loads(labels_path.read_text(encoding="utf-8"))
            classes = data.get("classes") or []
            if isinstance(classes, list) and classes:
                return len(classes)
        except Exception:
            logger.exception("Could not read labels.json")
    metrics = _load_metrics()
    classes = metrics.get("classes") or []
    if isinstance(classes, list) and classes:
        return len(classes)
    return 3


def model_accuracy_label() -> str:
    """Format held-out test accuracy from the latest training metrics.json."""
    metrics = _load_metrics()
    value = metrics.get("test_accuracy")
    if value is None:
        history = metrics.get("history") or {}
        vals = history.get("val_accuracy") or []
        if vals:
            value = vals[-1]
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "—"
    if not (0.0 <= score <= 1.0):
        return "—"
    return f"{round(score * 100):.0f}%"


def dashboard_stats(user: CustomerUser) -> dict:
    total = Classification.query.filter_by(user_id=user.id).count()
    recent = (
        Classification.query.filter_by(user_id=user.id)
        .order_by(Classification.created_at.desc())
        .limit(5)
        .all()
    )
    return {
        "textile_types": _load_class_count(),
        "model_accuracy": model_accuracy_label(),
        "images_classified": total,
        "recent": [
            {
                "label": row.display_name or row.predicted_label,
                "confidence": row.confidence,
                "image_name": row.image_name,
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
            for row in recent
        ],
    }
