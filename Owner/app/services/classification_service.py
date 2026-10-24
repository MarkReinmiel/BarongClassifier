"""Owner textile classification using the local Keras model (or classify server)."""

from __future__ import annotations

import base64
import io
import logging
import math
import uuid
from pathlib import Path

import httpx
from flask import current_app
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import OwnerUser, utcnow

logger = logging.getLogger("owner.classify")
OWNER_ROOT = Path(__file__).resolve().parents[2]


class ClassificationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def validate_confidence(value) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError) as error:
        raise ClassificationError("The model returned an invalid confidence value.") from error
    if not math.isfinite(confidence) or confidence < 0 or confidence > 1:
        raise ClassificationError("Confidence must be between 0 and 1.")
    return confidence


def prepare_image_bytes(file_storage) -> bytes:
    filename = (getattr(file_storage, "filename", "") or "").lower()
    suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    allowed = {".jpg", ".jpeg", ".jpe", ".png", ".webp"}
    if suffix not in allowed:
        raise ClassificationError("Use a JPG, JPEG, JPE, PNG, or WEBP image.")

    raw = file_storage.read()
    max_bytes = current_app.config.get("MAX_CONTENT_LENGTH") or 10 * 1024 * 1024
    if len(raw) > max_bytes:
        raise ClassificationError("That image is too large.")

    image = Image.open(io.BytesIO(raw)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _model_file() -> Path | None:
    configured = current_app.config.get("MODEL_PATH") or "models/barong_model.keras"
    candidate = Path(configured)
    if not candidate.is_file():
        candidate = OWNER_ROOT / candidate
    return candidate if candidate.is_file() else None


def _predict_local(content: bytes) -> tuple[str, float] | None:
    model_path = _model_file()
    if model_path is None:
        return None
    try:
        from app.ml.predictor import predict

        return predict(content, model_path=str(model_path), customer_root=OWNER_ROOT)
    except Exception:
        logger.exception("Local CNN prediction failed.")
        return None


def _predict_remote(content: bytes) -> tuple[str, float] | None:
    url = (current_app.config.get("CLASSIFY_SERVER_URL") or "").strip()
    if not url:
        return None
    display = {"pina": "Piña", "jusi": "Jusi", "cocoon": "Cocoon"}
    encoded = base64.b64encode(content).decode("ascii")
    try:
        response = httpx.post(url, json={"image": encoded}, timeout=60.0)
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
        logger.warning("Classify server was unavailable.")
    return None


def classify_upload(user: OwnerUser, file_storage) -> dict:
    if not user or not user.id:
        raise ClassificationError("Sign in again.", 401)

    name = getattr(file_storage, "filename", None) or "upload.jpg"
    content = prepare_image_bytes(file_storage)

    result = _predict_local(content) or _predict_remote(content)
    if result is None:
        raise ClassificationError(
            "No classifier is available. Place models/barong_model.keras or set CLASSIFY_SERVER_URL.",
            503,
        )

    label, confidence = result
    confidence = validate_confidence(confidence)
    label_text = str(label).strip()
    display = {
        "pina": "Piña",
        "piña": "Piña",
        "jusi": "Jusi",
        "cocoon": "Cocoon",
    }.get(label_text.lower(), label_text)
    row_id = str(uuid.uuid4())

    from app.services.cloudinary_service import upload_classification_image

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

    # Persist into public.classifications so rows appear in Supabase Table Editor.
    try:
        from sqlalchemy import text

        db.session.execute(
            text(
                """
                insert into public.classifications
                  (
                    id, user_id, file_name, predicted_label, display_name, confidence,
                    created_at, image_path, predicted_textile_type, confidence_score, image_reference
                  )
                values
                  (
                    cast(:id as uuid), cast(:user_id as uuid), :file_name, :label, :display_name,
                    :confidence, now(), :image_path, :label, :confidence, :image_reference
                  )
                """
            ),
            {
                "id": row_id,
                "user_id": str(user.id),
                "file_name": name,
                "label": label_text,
                "display_name": display,
                "confidence": confidence,
                # image_path / image_reference get the Cloudinary secure_url only.
                # Filename stays in file_name so the sync trigger cannot promote a bare name.
                "image_path": image_url,
                "image_reference": image_url,
            },
        )
        db.session.commit()
        logger.info(
            "classification_db_ok id=%s image_path_set=%s",
            row_id,
            bool(image_url),
        )
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Classification history was not saved. id=%s", row_id)

    image_b64 = base64.b64encode(content).decode("ascii")
    payload = {
        "label": display,
        "confidence": confidence,
        "image_name": name,
        "created_at": utcnow().isoformat(),
        "image_data_url": f"data:image/jpeg;base64,{image_b64}",
        "image_path": image_url,
    }
    payload.update(_hierarchical_result(display, confidence, image_bytes=content))
    return payload


def _model_version() -> str:
    labels_path = OWNER_ROOT / "models" / "labels.json"
    try:
        import json

        data = json.loads(labels_path.read_text(encoding="utf-8"))
        return str(data.get("version") or "")
    except Exception:
        return ""


def _hierarchical_result(
    display_label: str, confidence: float, image_bytes: bytes | None = None
) -> dict:
    raw = str(display_label or "").strip().lower().replace("ñ", "n")
    display_map = {"pina": "Piña", "jusi": "Jusi", "cocoon": "Cocoon"}
    variant = "undetermined"
    variant_display = "Undetermined"
    variant_confidence = None
    message = ""
    status = "classified"

    if "pina" in raw:
        main_key = "pina"
        variant_hit = None
        if image_bytes:
            try:
                from app.ml.variant_predictor import load_variant_model, predict_variant

                load_variant_model(
                    OWNER_ROOT,
                    configured=current_app.config.get("VARIANT_MODEL_PATH"),
                )
                variant_hit = predict_variant(image_bytes)
            except Exception:
                logger.exception("Variant model unavailable.")
        if variant_hit:
            variant = variant_hit["variant"]
            variant_display = variant_hit["variant_label"]
            variant_confidence = variant_hit.get("variant_confidence")
            message = variant_hit.get("message") or ""
            if variant_hit.get("status") == "uncertain":
                status = "uncertain"
        else:
            message = (
                "Piña detected, but the Piña / Piña Silk variant could not be determined "
                "reliably yet."
            )
            status = "uncertain"
    elif "jusi" in raw:
        main_key = "jusi"
        variant = "not_applicable"
        variant_display = "Not applicable"
    elif "cocoon" in raw:
        main_key = "cocoon"
        variant = "not_applicable"
        variant_display = "Not applicable"
    else:
        main_key = raw or "unknown"
        message = "This image could not be classified reliably. Please capture another image."
        status = "uncertain"

    return {
        "main_class": main_key,
        "main_class_label": display_map.get(main_key, display_label),
        "variant": variant,
        "variant_label": variant_display,
        "main_confidence": float(confidence),
        "variant_confidence": variant_confidence,
        "status": status if main_key in {"pina", "jusi", "cocoon"} else "uncertain",
        "message": message,
        "model_version": _model_version(),
    }
