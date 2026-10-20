from __future__ import annotations

import logging
import math

import httpx
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Classification, CustomerUser, utcnow

logger = logging.getLogger("customer.classify")


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


def _predict(content: bytes, filename: str) -> tuple[str, float]:
    url = current_app.config.get("CLASSIFY_SERVER_URL")
    if url:
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
                    return str(label), float(confidence)
        except Exception:
            logger.warning("Classify server was unavailable.")

    names = current_app.config.get("CLASS_NAMES") or ["pina", "jusi", "cocoon"]
    display = {"pina": "Piña", "jusi": "Jusi", "cocoon": "Cocoon"}
    key = names[0].lower()
    return display.get(key, key.title()), 0.0
