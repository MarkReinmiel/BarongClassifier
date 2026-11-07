"""Validate images and encode WebP without Flask or TensorFlow dependencies."""

from __future__ import annotations

import io
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError

from shared.image_processing.errors import ImageProcessingError
from shared.image_processing.result import ConversionResult
from shared.image_processing.settings import WebPSettings

# Reject truncated / bombs early; do not allow truncated-image decoding.
ImageFile.LOAD_TRUNCATED_IMAGES = False

SUPPORTED_FORMATS = frozenset({"JPEG", "PNG", "BMP", "WEBP"})
SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".jpe", ".png", ".bmp", ".webp"})

# Cap Pillow's decompression-bomb guard; callers can tighten via max_width/height.
_DEFAULT_MAX_PIXELS = 60_000_000  # 6000x6000 * ~1.6 headroom


def _read_input(input_image: bytes | bytearray | memoryview | str | Path | BinaryIO) -> bytes:
    if isinstance(input_image, (bytes, bytearray, memoryview)):
        return bytes(input_image)
    if isinstance(input_image, (str, Path)):
        path = Path(input_image)
        try:
            return path.read_bytes()
        except OSError as error:
            raise ImageProcessingError(f"Could not read image file: {error}") from error
    read = getattr(input_image, "read", None)
    if not callable(read):
        raise ImageProcessingError("Unsupported image input type.")
    data = read()
    if not isinstance(data, (bytes, bytearray)):
        raise ImageProcessingError("Image stream did not return bytes.")
    return bytes(data)


def _flatten_to_rgb(image: Image.Image, background_rgb: tuple[int, int, int]) -> Image.Image:
    """Produce an owned RGB image; composite transparency onto a solid background."""
    if image.mode == "RGB":
        return image.copy()

    if image.mode in {"RGBA", "LA"}:
        rgba = image.convert("RGBA") if image.mode == "LA" else image
        background = Image.new("RGBA", rgba.size, (*background_rgb, 255))
        composited = Image.alpha_composite(background, rgba)
        rgb = composited.convert("RGB")
        if rgba is not image:
            rgba.close()
        background.close()
        composited.close()
        return rgb

    if image.mode == "P":
        if "transparency" in image.info:
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (*background_rgb, 255))
            composited = Image.alpha_composite(background, rgba)
            rgb = composited.convert("RGB")
            rgba.close()
            background.close()
            composited.close()
            return rgb
        return image.convert("RGB")

    if image.mode == "CMYK":
        return image.convert("RGB")

    return image.convert("RGB")


def convert_to_webp(
    input_image: bytes | bytearray | memoryview | str | Path | BinaryIO,
    *,
    quality: int | None = None,
    lossless: bool | None = None,
    method: int | None = None,
    settings: WebPSettings | None = None,
) -> ConversionResult:
    """Validate image bytes/path/stream and return WebP bytes plus metadata.

    Does not resize. Does not mutate the source file.
    """
    cfg = settings or WebPSettings()
    use_quality = int(cfg.quality if quality is None else quality)
    use_lossless = bool(cfg.lossless if lossless is None else lossless)
    use_method = int(cfg.method if method is None else method)
    if not 0 <= use_quality <= 100:
        raise ImageProcessingError("quality must be between 0 and 100.")
    if not 0 <= use_method <= 6:
        raise ImageProcessingError("method must be between 0 and 6.")

    raw = _read_input(input_image)
    original_size = len(raw)
    if original_size == 0:
        raise ImageProcessingError("Image is empty.")
    if original_size > int(cfg.max_upload_bytes):
        mb = cfg.max_upload_bytes / (1024 * 1024)
        raise ImageProcessingError(f"Image exceeds the maximum upload size ({mb:g} MB).")

    previous_max_pixels = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = min(int(previous_max_pixels or _DEFAULT_MAX_PIXELS), _DEFAULT_MAX_PIXELS)
    try:
        try:
            with Image.open(io.BytesIO(raw)) as opened:
                opened.load()  # force decode; catch truncated/corrupt payloads
                source_format = (opened.format or "").upper() or None
                if source_format == "JPG":
                    source_format = "JPEG"
                if source_format not in SUPPORTED_FORMATS:
                    raise ImageProcessingError(
                        f"Unsupported image format {source_format or 'unknown'}. "
                        "Use JPEG, PNG, BMP, or WebP."
                    )

                # EXIF orientation before size checks so dimensions match display.
                oriented = ImageOps.exif_transpose(opened)
                # exif_transpose may return the same object; copy bitmap we own.
                working = oriented.copy() if oriented is not None else opened.copy()

                width, height = working.size
                if width > int(cfg.max_width) or height > int(cfg.max_height):
                    raise ImageProcessingError(
                        f"Image dimensions {width}×{height} exceed the maximum "
                        f"{cfg.max_width}×{cfg.max_height}."
                    )

                rgb = _flatten_to_rgb(working, cfg.background_rgb)
                if working is not rgb:
                    working.close()

                out = io.BytesIO()
                save_kwargs: dict = {
                    "format": "WEBP",
                    "method": use_method,
                }
                if use_lossless:
                    save_kwargs["lossless"] = True
                else:
                    save_kwargs["quality"] = use_quality
                    save_kwargs["lossless"] = False

                try:
                    rgb.save(out, **save_kwargs)
                    content = out.getvalue()
                    return ConversionResult(
                        content=content,
                        width=rgb.size[0],
                        height=rgb.size[1],
                        mode=rgb.mode,
                        source_format=source_format,
                        original_size_bytes=original_size,
                        output_size_bytes=len(content),
                        quality=None if use_lossless else use_quality,
                        lossless=use_lossless,
                        method=use_method,
                    )
                finally:
                    rgb.close()
        except ImageProcessingError:
            raise
        except UnidentifiedImageError as error:
            raise ImageProcessingError("File is not a recognizable image.") from error
        except Image.DecompressionBombError as error:
            raise ImageProcessingError("Image is too large to process safely.") from error
        except OSError as error:
            # Truncated / corrupt decode often surfaces as OSError from Pillow.
            raise ImageProcessingError(f"Could not decode image: {error}") from error
        except ValueError as error:
            raise ImageProcessingError(f"Could not process image: {error}") from error
    finally:
        Image.MAX_IMAGE_PIXELS = previous_max_pixels
