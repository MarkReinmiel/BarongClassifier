"""Confidence-based textile identification (not OOD detection).

Rule: if highest-class confidence is below IDENTIFY_MIN_CONFIDENCE (0.80),
the customer-facing result is Unidentified Textile. The original CNN class and
confidence are preserved for history / Owner inspection.
"""

from __future__ import annotations

IDENTIFY_MIN_CONFIDENCE = 0.80  # below this → unidentified; 80% and above → identified
DISPLAY_UNIDENTIFIED = "Unidentified Textile"
STATUS_UNIDENTIFIED = "unidentified_textile"
STATUS_CLASSIFIED = "classified"

_CLASS_KEYS = ("pina", "jusi", "cocoon")
_DISPLAY = {"pina": "Piña", "jusi": "Jusi", "cocoon": "Cocoon"}


def normalize_class_key(label: str | None) -> str:
    raw = str(label or "").strip().lower().replace("ñ", "n").replace("piña", "pina")
    for key in _CLASS_KEYS:
        if key in raw:
            return key
    return raw or "unknown"


def display_name_for_key(key: str, fallback: str | None = None) -> str:
    return _DISPLAY.get(key, fallback or key or "Unknown")


def apply_confidence_identification(
    *,
    predicted_label: str,
    predicted_display: str,
    confidence: float,
) -> dict:
    """Map a CNN prediction into customer-facing identification fields.

    ``confidence`` must already be on the 0–1 scale used by the model.
    """
    conf = float(confidence)
    predicted_key = normalize_class_key(predicted_label) or normalize_class_key(predicted_display)
    predicted_show = display_name_for_key(predicted_key, predicted_display)
    is_identified = conf >= float(IDENTIFY_MIN_CONFIDENCE)

    if is_identified and predicted_key in _CLASS_KEYS:
        return {
            "predicted_class": predicted_key,
            "predicted_display": predicted_show,
            "displayed_class": predicted_key,
            "display_name": predicted_show,
            "label": predicted_show,
            "is_identified": True,
            "status": STATUS_CLASSIFIED,
            "message": "",
            "confidence": conf,
            "confidence_threshold": float(IDENTIFY_MIN_CONFIDENCE),
            "main_class": predicted_key,
            "main_class_label": predicted_show,
        }

    return {
        "predicted_class": predicted_key if predicted_key in _CLASS_KEYS else predicted_key,
        "predicted_display": predicted_show,
        "displayed_class": STATUS_UNIDENTIFIED,
        "display_name": DISPLAY_UNIDENTIFIED,
        "label": DISPLAY_UNIDENTIFIED,
        "is_identified": False,
        "status": STATUS_UNIDENTIFIED,
        "message": (
            "The system could not confidently identify the textile type "
            "from the submitted image."
        ),
        "confidence": conf,
        "confidence_threshold": float(IDENTIFY_MIN_CONFIDENCE),
        "main_class": predicted_key if predicted_key in _CLASS_KEYS else "unknown",
        "main_class_label": DISPLAY_UNIDENTIFIED,
    }
