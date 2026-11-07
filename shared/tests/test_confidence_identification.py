"""Boundary tests for confidence-based Unidentified Textile (0–1 confidence scale)."""

from __future__ import annotations

import unittest

from shared.confidence_identification import (
    DISPLAY_UNIDENTIFIED,
    IDENTIFY_MIN_CONFIDENCE,
    STATUS_CLASSIFIED,
    STATUS_UNIDENTIFIED,
    apply_confidence_identification,
)


class ConfidenceIdentificationTests(unittest.TestCase):
    def test_threshold_constant(self):
        self.assertEqual(IDENTIFY_MIN_CONFIDENCE, 0.80)

    def _case(self, confidence: float, *, identified: bool):
        result = apply_confidence_identification(
            predicted_label="pina",
            predicted_display="Piña",
            confidence=confidence,
        )
        self.assertEqual(result["predicted_class"], "pina")
        self.assertEqual(result["predicted_display"], "Piña")
        self.assertEqual(result["confidence"], confidence)
        self.assertEqual(result["confidence_threshold"], 0.80)
        if identified:
            self.assertTrue(result["is_identified"])
            self.assertEqual(result["status"], STATUS_CLASSIFIED)
            self.assertEqual(result["label"], "Piña")
            self.assertEqual(result["displayed_class"], "pina")
        else:
            self.assertFalse(result["is_identified"])
            self.assertEqual(result["status"], STATUS_UNIDENTIFIED)
            self.assertEqual(result["label"], DISPLAY_UNIDENTIFIED)
            self.assertEqual(result["displayed_class"], STATUS_UNIDENTIFIED)

    def test_100_percent_identified(self):
        self._case(1.0, identified=True)

    def test_95_percent_identified(self):
        self._case(0.95, identified=True)

    def test_80_percent_identified(self):
        self._case(0.80, identified=True)

    def test_8001_percent_identified(self):
        self._case(0.8001, identified=True)

    def test_7999_percent_unidentified(self):
        self._case(0.7999, identified=False)

    def test_75_percent_unidentified(self):
        self._case(0.75, identified=False)

    def test_50_percent_unidentified(self):
        self._case(0.50, identified=False)


if __name__ == "__main__":
    unittest.main()
