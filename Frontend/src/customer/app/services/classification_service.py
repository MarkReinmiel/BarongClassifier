from __future__ import annotations

import base64
import logging
import math
import uuid
from pathlib import Path

import httpx
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Classification, CustomerUser, utcnow

logger = logging.getLogger("customer.classify")
CUSTOMER_ROOT = Path(__file__).resolve().parents[2]

_DISPLAY = {"pina": "Piña", "piña": "Piña", "jusi": "Jusi", "cocoon": "Cocoon"}


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


def display_name_for(label: str) -> str:
    key = str(label or "").strip().lower()
    return _DISPLAY.get(key, str(label or "").strip() or "Unknown")


def _model_version() -> str:
    labels_path = CUSTOMER_ROOT / "models" / "labels.json"
    try:
        import json

        data = json.loads(labels_path.read_text(encoding="utf-8"))
        return str(data.get("version") or "")
    except Exception:
        return ""


def hierarchical_result(
    display_label: str, confidence: float, image_bytes: bytes | None = None
) -> dict:
    """Main-class fields only (Piña Silk variant retired — silk folds into Piña)."""
    del image_bytes  # kept for call-site compatibility
    raw = str(display_label or "").strip().lower().replace("ñ", "n")
    message = ""
    status = "classified"

    if "pina" in raw:
        main_key = "pina"
    elif "jusi" in raw:
        main_key = "jusi"
    elif "cocoon" in raw:
        main_key = "cocoon"
    else:
        main_key = raw or "unknown"
        message = "This image could not be classified reliably. Please capture another image."
        status = "uncertain"

    return {
        "main_class": main_key,
        "main_class_label": display_name_for(main_key if main_key != "unknown" else display_label),
        "variant": "not_applicable",
        "variant_label": "Not applicable",
        "main_confidence": float(confidence),
        "variant_confidence": None,
        "status": status if main_key in {"pina", "jusi", "cocoon"} else "uncertain",
        "message": message,
        "model_version": _model_version(),
    }


def _persist_classification(
    *,
    user: CustomerUser,
    name: str,
    content: bytes,
    label_text: str,
    display: str,
    confidence: float,
) -> Classification:
    from app.services.cloudinary_service import upload_classification_image

    row_id = str(uuid.uuid4())
    now = utcnow()
    image_url = upload_classification_image(
        content=content,
        filename=name,
        user_id=str(user.id),
        classification_id=row_id,
    )
    if image_url:
        logger.info("classification_image_path_ready id=%s has_cloudinary_url=1", row_id)
    else:
        logger.warning(
            "classification_image_path_ready id=%s has_cloudinary_url=0 "
            "(DB will store NULL; classify still succeeds)",
            row_id,
        )

    row = Classification(
        id=row_id,
        user_id=str(user.id),
        file_name=name,
        predicted_label=label_text,
        display_name=display,
        confidence=confidence,
        image_path=image_url,
        predicted_textile_type=label_text,
        confidence_score=confidence,
        image_reference=image_url,
        created_at=now,
    )
    db.session.add(row)
    try:
        db.session.commit()
        logger.info(
            "classification_db_ok id=%s image_path_set=%s status_label=%s",
            row_id,
            bool(image_url),
            label_text,
        )
    except SQLAlchemyError as error:
        db.session.rollback()
        logger.exception("Classification history was not saved. id=%s", row_id)
        raise ClassificationError("The classification could not be saved.", 503) from error
    return row


def classify_image(user: CustomerUser, file_storage) -> dict:
    from app.services.image_service import prepare_image_bytes
    from app.ml.relevance_gate import (
        DISPLAY_UNDEFINED,
        STATUS_CLASSIFIED,
        assess_relevance,
    )

    if not user or not user.id:
        raise ClassificationError("Sign in again.", 401)

    name = getattr(file_storage, "filename", None) or "upload.jpg"
    content = prepare_image_bytes(file_storage)

    model = None
    model_path = _model_file()
    gate_enabled = bool(current_app.config.get("RELEVANCE_GATE_ENABLED", False))
    gate = None
    if gate_enabled:
        if model_path is not None:
            try:
                from app.ml.predictor import ensure_model

                model = ensure_model(str(model_path), customer_root=CUSTOMER_ROOT)
            except Exception:
                logger.exception("Could not load local model for relevance gate.")

        gate = assess_relevance(
            content,
            model=model,
            model_path=str(model_path) if model_path else None,
            app_root=CUSTOMER_ROOT,
            enabled=True,
        )
    else:
        logger.info("relevance_gate_skipped RELEVANCE_GATE_ENABLED=false")

    if gate is not None and not gate.accept_textile:
        # Never assign Piña / Jusi / Cocoon for rejected relevance outcomes.
        label_text = "undefined_textile"
        display = DISPLAY_UNDEFINED
        confidence = validate_confidence(max(0.0, min(1.0, float(gate.confidence))))
        row = _persist_classification(
            user=user,
            name=name,
            content=content,
            label_text=label_text,
            display=display,
            confidence=confidence,
        )
        image_b64 = base64.b64encode(content).decode("ascii")
        payload = {
            "id": str(row.id),
            "label": display,
            "confidence": float(row.confidence),
            "image_name": row.image_name,
            "image_path": row.image_path,
            "image_data_url": f"data:image/jpeg;base64,{image_b64}",
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "model_version": _model_version(),
        }
        payload.update(gate.as_result_fields())
        payload["label"] = display
        payload["confidence"] = float(row.confidence)
        return payload

    label, confidence = _predict(content, name)
    confidence = validate_confidence(confidence)
    if not label or not str(label).strip():
        raise ClassificationError("The model did not return a textile label.")

    label_text = str(label).strip()
    display = display_name_for(label_text)
    row = _persist_classification(
        user=user,
        name=name,
        content=content,
        label_text=label_text,
        display=display,
        confidence=confidence,
    )

    conf = float(row.confidence)
    display = row.display_name or row.predicted_label
    image_b64 = base64.b64encode(content).decode("ascii")
    payload = {
        "id": str(row.id),
        "label": display,
        "confidence": conf,
        "image_name": row.image_name,
        "image_path": row.image_path,
        "image_data_url": f"data:image/jpeg;base64,{image_b64}",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
    payload.update(hierarchical_result(display, conf, image_bytes=content))
    if gate is not None and gate.status == STATUS_CLASSIFIED:
        payload["gate"] = gate.details
    return payload


def _model_file() -> Path | None:
    configured = current_app.config.get("MODEL_PATH") or "models/barong_model.keras"
    configured_path = Path(configured)
    repo_root = CUSTOMER_ROOT.parents[2]  # Frontend/src/customer → repo root
    candidates = [
        configured_path if configured_path.is_absolute() else None,
        CUSTOMER_ROOT / configured_path,
        repo_root / "Customer" / "models" / "barong_model.keras",
        repo_root / "ml" / "models" / "active" / "main_classifier.keras",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    return None


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
