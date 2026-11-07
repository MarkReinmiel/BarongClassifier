"""Conversion result metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConversionResult:
    content: bytes
    width: int
    height: int
    mode: str
    source_format: str | None
    original_size_bytes: int
    output_size_bytes: int
    quality: int | None
    lossless: bool
    method: int
    output_format: str = "WEBP"

    @property
    def savings_bytes(self) -> int:
        return int(self.original_size_bytes) - int(self.output_size_bytes)

    @property
    def savings_ratio(self) -> float:
        if self.original_size_bytes <= 0:
            return 0.0
        return self.savings_bytes / float(self.original_size_bytes)
