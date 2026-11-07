"""Phase 3 bulk converter tests (tiny temp trees)."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.image_processing.bulk import convert_dataset_tree, write_report
from shared.image_processing.settings import WebPSettings


class BulkConvertTests(unittest.TestCase):
    def test_execute_writes_webp_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src"
            output = root / "out"
            (source / "pina").mkdir(parents=True)
            buf = io.BytesIO()
            Image.new("RGB", (32, 24), (1, 2, 3)).save(buf, format="JPEG", quality=90)
            original = source / "pina" / "a.jpg"
            original.write_bytes(buf.getvalue())
            before = original.read_bytes()

            report = convert_dataset_tree(
                source,
                output,
                settings=WebPSettings(quality=90),
                dry_run=False,
                skip_existing=True,
            )
            self.assertEqual(report.converted, 1)
            self.assertEqual(report.failed, 0)
            dest = output / "pina" / "a.webp"
            self.assertTrue(dest.is_file())
            self.assertEqual(original.read_bytes(), before)
            with Image.open(dest) as image:
                self.assertEqual(image.format, "WEBP")
                self.assertEqual(image.size, (32, 24))
            report_path = write_report(report, root / "report.json")
            self.assertTrue(report_path.is_file())

    def test_refuses_output_inside_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src"
            source.mkdir()
            with self.assertRaises(Exception):
                convert_dataset_tree(source, source / "nested", dry_run=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
