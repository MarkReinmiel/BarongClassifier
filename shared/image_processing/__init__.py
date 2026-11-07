"""Centralized image validation and WebP conversion.

Phase 1: ``convert_to_webp``
Phase 2: Customer/Owner upload prepare paths
Phase 3: bulk dataset conversion helpers (``bulk``)

    from shared.image_processing import convert_to_webp, WebPSettings
"""

from shared.image_processing.bulk import BulkConversionReport, convert_dataset_tree, write_report
from shared.image_processing.convert import convert_to_webp
from shared.image_processing.errors import ImageProcessingError
from shared.image_processing.result import ConversionResult
from shared.image_processing.settings import WebPSettings, settings_from_environ

__all__ = [
    "BulkConversionReport",
    "ConversionResult",
    "ImageProcessingError",
    "WebPSettings",
    "convert_dataset_tree",
    "convert_to_webp",
    "settings_from_environ",
    "write_report",
]
