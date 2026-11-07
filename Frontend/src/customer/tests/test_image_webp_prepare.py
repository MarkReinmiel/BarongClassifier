"""Phase 2: Customer prepare_image_bytes returns WebP."""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[4]
CUSTOMER_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, CUSTOMER_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402
from app.services.image_service import prepare_image_bytes  # noqa: E402


class _FakeStorage:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    def read(self):
        return self._content


class PrepareImageWebPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(TestConfig)

    def test_jpeg_upload_becomes_webp(self):
        buf = io.BytesIO()
        Image.new("RGB", (64, 48), (12, 34, 56)).save(buf, format="JPEG", quality=90)
        with self.app.app_context():
            out = prepare_image_bytes(_FakeStorage("shot.jpg", buf.getvalue()))
        self.assertTrue(out.startswith(b"RIFF"))
        with Image.open(io.BytesIO(out)) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (64, 48))

    def test_png_upload_becomes_webp(self):
        buf = io.BytesIO()
        Image.new("RGBA", (40, 40), (255, 0, 0, 128)).save(buf, format="PNG")
        with self.app.app_context():
            out = prepare_image_bytes(_FakeStorage("alpha.png", buf.getvalue()))
        with Image.open(io.BytesIO(out)) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.mode, "RGB")


if __name__ == "__main__":
    unittest.main(verbosity=2)
