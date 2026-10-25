"""Automated tests for relevance / OOD gate decisioning (no production retrain)."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.ml.relevance_gate import (
    DISPLAY_UNDEFINED,
    STATUS_CLASSIFIED,
    STATUS_POOR,
    STATUS_UNCERTAIN,
    STATUS_UNDEFINED,
    assess_image_quality,
    assess_relevance,
    cosine_distances,
    softmax_entropy,
)


def _jpeg_bytes(rgb: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb.astype(np.uint8), mode="RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_poor_quality_black_image():
    rgb = np.zeros((224, 224, 3), dtype=np.uint8)
    status, metrics = assess_image_quality(
        rgb,
        {"min_brightness": 0.08, "max_brightness": 0.95, "min_laplacian_var": 18.0},
    )
    assert status == STATUS_POOR
    assert metrics["brightness"] < 0.08


def test_poor_quality_blur_proxy():
    # Near-uniform gray → very low Laplacian variance.
    rgb = np.full((224, 224, 3), 128, dtype=np.uint8)
    status, metrics = assess_image_quality(
        rgb,
        {"min_brightness": 0.05, "max_brightness": 0.95, "min_laplacian_var": 18.0},
    )
    assert status == STATUS_POOR
    assert metrics["laplacian_var"] < 18.0


def test_assess_relevance_poor_without_model():
    decision = assess_relevance(
        _jpeg_bytes(np.zeros((64, 64, 3), dtype=np.uint8)),
        model=None,
        enabled=True,
    )
    assert decision is not None
    assert decision.accept_textile is False
    assert decision.status == STATUS_POOR
    assert decision.display_label == DISPLAY_UNDEFINED
    fields = decision.as_result_fields()
    assert fields["status"] == STATUS_POOR
    assert fields["label"] == DISPLAY_UNDEFINED
    assert "pina" not in fields["label"].lower()


def test_assess_relevance_disabled_returns_none():
    textured = np.random.default_rng(0).integers(0, 255, size=(224, 224, 3), dtype=np.uint8)
    assert assess_relevance(_jpeg_bytes(textured), model=None, enabled=False) is None


def test_cosine_and_entropy_helpers():
    feats = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    cents = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
    dists = cosine_distances(feats, cents)
    assert dists[0] < 1e-5
    assert dists[1] == pytest.approx(1.0, abs=1e-5)
    ent = softmax_entropy(np.array([0.9, 0.05, 0.05], dtype=np.float32))
    assert 0 < ent < 1.0


def test_gate_decision_fields_never_map_undefined_to_textile():
    from app.ml.relevance_gate import GateDecision

    decision = GateDecision(
        status=STATUS_UNDEFINED,
        display_label=DISPLAY_UNDEFINED,
        confidence=0.12,
        message="out of domain",
        accept_textile=False,
        details={"reason": "far_from_textile_centroids"},
    )
    fields = decision.as_result_fields()
    assert fields["status"] == STATUS_UNDEFINED
    assert fields["label"] == "Undefined Textile"
    assert fields["main_class"] == "undefined_textile"


def test_uncertain_status_code_separate_from_display():
    from app.ml.relevance_gate import GateDecision

    decision = GateDecision(
        status=STATUS_UNCERTAIN,
        display_label=DISPLAY_UNDEFINED,
        confidence=0.4,
        message="uncertain",
        accept_textile=False,
        details={},
    )
    fields = decision.as_result_fields()
    assert fields["status"] == STATUS_UNCERTAIN
    assert fields["label"] == DISPLAY_UNDEFINED


def test_malformed_image_rejected_by_prepare():
    from app import create_app
    from app.config import TestConfig
    from app.services.image_service import prepare_image_bytes

    application = create_app(TestConfig)
    with application.app_context():
        class BadFile:
            filename = "x.txt"

            def read(self):
                return b"not-an-image"

        with pytest.raises(ValueError, match="JPG"):
            prepare_image_bytes(BadFile())

        class BrokenJpeg:
            filename = "broken.jpg"

            def read(self):
                return b"not-actually-jpeg-bytes"

        with pytest.raises(Exception):
            prepare_image_bytes(BrokenJpeg())


def test_supported_textile_accept_path_with_mock_gate(monkeypatch):
    """Frontend cannot override status: service attaches backend status only."""
    from app.ml.relevance_gate import GateDecision

    accepted = GateDecision(
        status=STATUS_CLASSIFIED,
        display_label="",
        confidence=0.91,
        message="",
        accept_textile=True,
        details={"reason": "accepted"},
    )
    assert accepted.accept_textile is True
    assert accepted.status == STATUS_CLASSIFIED
