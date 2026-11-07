"""Phase 1 tests for shared WebP conversion (no Flask / no CNN)."""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.image_processing import (  # noqa: E402
    ConversionResult,
    ImageProcessingError,
    WebPSettings,
    convert_to_webp,
)


def _encode(image: Image.Image, fmt: str, **kwargs) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def _checker(size=(120, 80), mode="RGB") -> Image.Image:
    image = Image.new(mode if mode != "RGBA" else "RGBA", size, (20, 40, 60, 255) if mode == "RGBA" else (20, 40, 60))
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 50, 50), fill=(200, 30, 30) if mode != "RGBA" else (200, 30, 30, 255))
    draw.rectangle((60, 20, 110, 70), fill=(30, 180, 40) if mode != "RGBA" else (30, 180, 40, 128))
    return image


class ConvertToWebPTests(unittest.TestCase):
    def test_jpeg_to_webp_preserves_dimensions(self) -> None:
        src = _encode(_checker((160, 90)), "JPEG", quality=95)
        result = convert_to_webp(src, quality=90)
        self.assertIsInstance(result, ConversionResult)
        self.assertEqual(result.width, 160)
        self.assertEqual(result.height, 90)
        self.assertEqual(result.mode, "RGB")
        self.assertEqual(result.source_format, "JPEG")
        self.assertEqual(result.output_format, "WEBP")
        self.assertFalse(result.lossless)
        self.assertEqual(result.quality, 90)
        with Image.open(io.BytesIO(result.content)) as out:
            self.assertEqual(out.format, "WEBP")
            self.assertEqual(out.size, (160, 90))

    def test_png_to_webp(self) -> None:
        src = _encode(_checker((100, 100)), "PNG")
        result = convert_to_webp(src)
        with Image.open(io.BytesIO(result.content)) as out:
            self.assertEqual(out.format, "WEBP")
            self.assertEqual(out.size, (100, 100))
        self.assertEqual(result.source_format, "PNG")

    def test_bmp_to_webp(self) -> None:
        src = _encode(_checker((64, 48)), "BMP")
        result = convert_to_webp(src)
        self.assertEqual(result.source_format, "BMP")
        with Image.open(io.BytesIO(result.content)) as out:
            self.assertEqual(out.format, "WEBP")
            self.assertEqual(out.size, (64, 48))

    def test_webp_passthrough_reencode(self) -> None:
        src = _encode(_checker((70, 70)), "WEBP", quality=90)
        result = convert_to_webp(src, quality=90)
        self.assertEqual(result.source_format, "WEBP")
        with Image.open(io.BytesIO(result.content)) as out:
            self.assertEqual(out.format, "WEBP")

    def test_rgba_transparency_becomes_rgb(self) -> None:
        rgba = _checker((80, 80), mode="RGBA")
        src = _encode(rgba, "PNG")
        result = convert_to_webp(src, quality=90)
        self.assertEqual(result.mode, "RGB")
        with Image.open(io.BytesIO(result.content)) as out:
            self.assertEqual(out.mode, "RGB")
            # Semi-transparent green rectangle should be blended toward white bg.
            pixel = out.getpixel((70, 45))
            self.assertGreater(pixel[1], 100)

    def test_exif_orientation_transpose(self) -> None:
        # Wide red bar on left; after Orientation=6 (rotate 90 CW) display is tall.
        base = Image.new("RGB", (80, 40), (0, 0, 0))
        draw = ImageDraw.Draw(base)
        draw.rectangle((0, 0, 20, 40), fill=(255, 0, 0))
        exif = Image.Exif()
        exif[0x0112] = 6  # Rotate 90 CW
        buf = io.BytesIO()
        base.save(buf, format="JPEG", quality=95, exif=exif)
        result = convert_to_webp(buf.getvalue())
        self.assertEqual((result.width, result.height), (40, 80))
        with Image.open(io.BytesIO(result.content)) as out:
            # Red should dominate the top rows after transpose.
            top = out.getpixel((20, 5))
            bottom = out.getpixel((20, 70))
            self.assertGreater(top[0], 200)
            self.assertLess(bottom[0], 50)

    def test_rejects_empty(self) -> None:
        with self.assertRaises(ImageProcessingError):
            convert_to_webp(b"")

    def test_rejects_corrupt(self) -> None:
        with self.assertRaises(ImageProcessingError):
            convert_to_webp(b"not-an-image")

    def test_rejects_truncated_jpeg(self) -> None:
        full = _encode(_checker((100, 100)), "JPEG", quality=90)
        with self.assertRaises(ImageProcessingError):
            convert_to_webp(full[:40])

    def test_rejects_oversized_bytes(self) -> None:
        settings = WebPSettings(max_upload_bytes=100)
        payload = _encode(_checker((50, 50)), "PNG")
        self.assertGreater(len(payload), 100)
        with self.assertRaises(ImageProcessingError):
            convert_to_webp(payload, settings=settings)

    def test_rejects_oversized_dimensions(self) -> None:
        settings = WebPSettings(max_width=50, max_height=50)
        payload = _encode(_checker((80, 80)), "PNG")
        with self.assertRaises(ImageProcessingError):
            convert_to_webp(payload, settings=settings)

    def test_quality_affects_size(self) -> None:
        src = _encode(_checker((240, 180)), "JPEG", quality=95)
        q60 = convert_to_webp(src, quality=60, lossless=False)
        q95 = convert_to_webp(src, quality=95, lossless=False)
        self.assertLess(q60.output_size_bytes, q95.output_size_bytes)

    def test_lossless_option(self) -> None:
        src = _encode(_checker((90, 90)), "PNG")
        result = convert_to_webp(src, lossless=True)
        self.assertTrue(result.lossless)
        self.assertIsNone(result.quality)
        with Image.open(io.BytesIO(result.content)) as out:
            self.assertEqual(out.format, "WEBP")

    def test_path_and_stream_inputs(self) -> None:
        src = _encode(_checker((32, 32)), "PNG")
        tmp = Path(__file__).with_name("_tmp_sample.png")
        try:
            tmp.write_bytes(src)
            from_path = convert_to_webp(tmp)
            from_stream = convert_to_webp(io.BytesIO(src))
            self.assertEqual(from_path.width, 32)
            self.assertEqual(from_stream.width, 32)
        finally:
            if tmp.exists():
                tmp.unlink()

    def test_sample_size_report_values(self) -> None:
        """Record sample sizes for the Phase 1 deliverable (assertion = valid WebP)."""
        samples = {
            "JPEG": _encode(_checker((320, 240)), "JPEG", quality=92),
            "PNG": _encode(_checker((320, 240)), "PNG"),
            "BMP": _encode(_checker((320, 240)), "BMP"),
            "WEBP": _encode(_checker((320, 240)), "WEBP", quality=90),
        }
        print("\nSample input -> WebP q90 sizes:")
        for label, payload in samples.items():
            result = convert_to_webp(payload, quality=90, lossless=False)
            print(
                f"  {label}: in={result.original_size_bytes}B "
                f"out={result.output_size_bytes}B "
                f"({result.savings_ratio * 100:.1f}% delta)"
            )
            self.assertTrue(result.content[:4] == b"RIFF")


class MemorySmokeTests(unittest.TestCase):
    def test_conversion_rss_delta_reasonable(self) -> None:
        try:
            import psutil
        except ImportError:
            self.skipTest("psutil not installed")
        proc = psutil.Process()
        before = proc.memory_info().rss
        src = _encode(_checker((800, 600)), "JPEG", quality=90)
        for _ in range(20):
            convert_to_webp(src, quality=90)
        after = proc.memory_info().rss
        delta_mb = (after - before) / (1024 * 1024)
        # Allow some allocator growth; flag pathological leaks only.
        self.assertLess(delta_mb, 80.0, f"RSS grew by {delta_mb:.1f} MB over 20 converts")


if __name__ == "__main__":
    unittest.main(verbosity=2)
