from __future__ import annotations

import base64
import logging
import math
from pathlib import Path

import httpx
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Classification, CustomerUser, utcnow

logger = logging.getLogger("customer.classify")
CUSTOMER_ROOT = Path(__file__).resolve().parents[2]


class ClassificationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def validate_confidence(value) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError) as error:
        raise ClassificationError("The model returned an invalid confidence value.") from error
    if not math.isfinite(confidence):
        raise ClassificationError("The model returned a non-finite confidence value.")
    if confidence < 0 or confidence > 1:
        raise ClassificationError("Confidence must be between 0 and 1.")
    return confidence


def classify_image(user: CustomerUser, file_storage) -> dict:
    from app.services.image_service import prepare_image_bytes

    if not user or not user.id:
        raise ClassificationError("Sign in again.", 401)

    name = getattr(file_storage, "filename", None) or "upload.jpg"
    content = prepare_image_bytes(file_storage)
    label, confidence = _predict(content, name)
    confidence = validate_confidence(confidence)
    if not label or not str(label).strip():
        raise ClassificationError("The model did not return a textile label.")

    row = Classification(
        user_id=user.id,
        predicted_label=str(label).strip(),
        confidence=confidence,
        image_name=name,
        role=user.role or "customer",
        status="completed",
        created_at=utcnow(),
    )
    db.session.add(row)
    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        logger.exception("Classification history was not saved.")
        raise ClassificationError("The classification could not be saved.", 503) from error

    return {
        "id": str(row.id),
        "label": row.predicted_label,
        "confidence": row.confidence,
        "image_name": row.image_name,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _model_file() -> Path | None:
    configured = current_app.config.get("MODEL_PATH") or "models/barong_model.keras"
    candidate = Path(configured)
    if not candidate.is_file():
        candidate = CUSTOMER_ROOT / candidate
    return candidate if candidate.is_file() else None


def _predict_local(content: bytes) -> tuple[str, float] | None:
    model_path = _model_file()
    if model_path is None:
        return None
    try:
        from app.ml.predictor import predict

        return predict(content, model_path=str(model_path), customer_root=CUSTOMER_ROOT)
    except Exception:
        logger.exception("Local CNN prediction failed.")
        return None


def _predict_remote(content: bytes, filename: str) -> tuple[str, float] | None:
    url = (current_app.config.get("CLASSIFY_SERVER_URL") or "").strip()
    if not url:
        return None

    display = {"pina": "Piña", "jusi": "Jusi", "cocoon": "Cocoon"}
    encoded = base64.b64encode(content).decode("ascii")
    try:
        response = httpx.post(
            url,
            json={"image": encoded},
            timeout=30.0,
        )
        if response.is_success:
            payload = response.json()
            label = (
                payload.get("display_name")
                or payload.get("label")
                or payload.get("predicted_label")
                or payload.get("class")
            )
            confidence = payload.get("confidence", payload.get("score", 0))
            if label is not None:
                key = str(label).strip()
                return display.get(key.lower(), key), float(confidence)
    except Exception:
        logger.warning("Classify server was unavailable at %s", url)

    # Legacy multipart fallback for alternate servers.
    try:
        response = httpx.post(
            url,
            files={"file": (filename, content, "image/jpeg")},
            timeout=30.0,
        )
        if response.is_success:
            payload = response.json()
            label = payload.get("label") or payload.get("predicted_label") or payload.get("class")
            confidence = payload.get("confidence", payload.get("score", 0))
            if label is not None:
                key = str(label).strip()
                return display.get(key.lower(), key), float(confidence)
    except Exception:
        logger.warning("Classify server multipart fallback failed.")
    return None


def _predict(content: bytes, filename: str) -> tuple[str, float]:
    local = _predict_local(content)
    if local is not None:
        return local

    remote = _predict_remote(content, filename)
    if remote is not None:
        return remote

    raise ClassificationError(
        "No classifier is available. Place models/barong_model.keras or set CLASSIFY_SERVER_URL.",
        503,
    )
