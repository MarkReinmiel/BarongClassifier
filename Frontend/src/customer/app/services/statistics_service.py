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


def _format_recent_when(created_at) -> str:
    if not created_at:
        return ""
    try:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        when = created_at
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        local = when.astimezone()
        today = now.astimezone().date()
        day = local.date()
        time_part = local.strftime("%I:%M %p").lstrip("0")
        if day == today:
            return f"Today, {time_part}"
        if (today - day).days == 1:
            return f"Yesterday, {time_part}"
        return local.strftime("%b %d, %I:%M %p").lstrip("0").replace(" 0", " ")
    except Exception:
        return ""


def dashboard_stats(user: CustomerUser) -> dict:
    from app.services.history_service import list_for_user

    # Same query path as History page so counts/recent never diverge.
    uid = str(user.id)
    total = Classification.query.filter(
        Classification.user_id.in_([uid, user.id])
    ).count()
    result = list_for_user(user, page=1, per_page=3)
    recent_rows = result.get("items") or []
    return {
        "textile_types": _load_class_count(),
        "model_accuracy": model_accuracy_label(),
        "images_classified": total,
        "recent": [
            {
                "label": row.display_name or row.predicted_label,
                "confidence": float(row.confidence or row.confidence_score or 0),
                "image_name": row.image_name or row.file_name or "image",
                "image_path": getattr(row, "image_url", None)
                or (row.image_path or row.image_reference or "")
                or "",
                "image_url": getattr(row, "image_url", None)
                or (row.image_path or row.image_reference or "")
                or "",
                "textile_key": (row.predicted_label or row.display_name or "")
                .strip()
                .lower()
                .replace("ñ", "n")
                .replace("piña", "pina"),
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "created_label": _format_recent_when(row.created_at),
            }
            for row in recent_rows
        ],
    }
