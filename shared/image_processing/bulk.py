"""Bulk dataset WebP conversion into a separate output tree (never overwrites source)."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from shared.image_processing.convert import SUPPORTED_EXTENSIONS, convert_to_webp
from shared.image_processing.errors import ImageProcessingError
from shared.image_processing.settings import WebPSettings

LogFn = Callable[[str], None]


@dataclass
class BulkConversionReport:
    source_root: str
    output_root: str
    dry_run: bool
    started_at: str
    finished_at: str | None = None
    quality: int = 90
    method: int = 6
    lossless: bool = False
    discovered: int = 0
    converted: int = 0
    skipped_existing: int = 0
    skipped_unsupported: int = 0
    failed: int = 0
    original_bytes: int = 0
    converted_bytes: int = 0
    per_class_counts: dict[str, int] = field(default_factory=dict)
    per_format_counts: dict[str, int] = field(default_factory=dict)
    failures: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def savings_bytes(self) -> int:
        return int(self.original_bytes) - int(self.converted_bytes)

    @property
    def savings_percent(self) -> float:
        if self.original_bytes <= 0:
            return 0.0
        return 100.0 * self.savings_bytes / float(self.original_bytes)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["savings_bytes"] = self.savings_bytes
        payload["savings_percent"] = round(self.savings_percent, 2)
        payload["savings_mb"] = round(self.savings_bytes / (1024 * 1024), 2)
        payload["original_mb"] = round(self.original_bytes / (1024 * 1024), 2)
        payload["converted_mb"] = round(self.converted_bytes / (1024 * 1024), 2)
        return payload


def iter_images(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def _rel_class(path: Path, source_root: Path) -> str:
    try:
        rel = path.relative_to(source_root)
    except ValueError:
        return "(root)"
    return rel.parts[0] if len(rel.parts) > 1 else "(root)"


def convert_dataset_tree(
    source_root: Path,
    output_root: Path,
    *,
    settings: WebPSettings | None = None,
    dry_run: bool = True,
    skip_existing: bool = True,
    estimate_sample: int = 0,
    log: LogFn | None = None,
) -> BulkConversionReport:
    """Copy directory structure under ``output_root`` with ``.webp`` files.

    Originals are never modified or deleted. Output is a sibling training tree
    that must be pointed at explicitly for training (not auto-merged).

    ``dry_run`` discovers files and optionally estimates sizes from
    ``estimate_sample`` conversions (0 = inventory only, no encode).
    """
    cfg = settings or WebPSettings()
    emit = log or (lambda _m: None)
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    if output_root == source_root or source_root in output_root.parents:
        raise ImageProcessingError(
            "output_root must be outside source_root (refusing to write into the source tree)."
        )

    started = datetime.now(timezone.utc).isoformat()
    report = BulkConversionReport(
        source_root=str(source_root),
        output_root=str(output_root),
        dry_run=dry_run,
        started_at=started,
        quality=cfg.quality,
        method=cfg.method,
        lossless=cfg.lossless,
    )
    report.notes.append(
        "Converted tree is separate from the live training dataset; "
        "do not mix original + WebP copies in one training run."
    )

    class_counts: Counter[str] = Counter()
    format_counts: Counter[str] = Counter()
    images = list(iter_images(source_root))
    estimate_budget = max(0, int(estimate_sample))
    estimated_out = 0
    estimated_in = 0
    estimated_n = 0

    for src in images:
        report.discovered += 1
        class_name = _rel_class(src, source_root)
        class_counts[class_name] += 1
        format_counts[src.suffix.lower()] += 1
        try:
            original_size = src.stat().st_size
        except OSError as error:
            report.failed += 1
            report.failures.append({"path": str(src), "error": str(error)[:300]})
            continue
        report.original_bytes += original_size

        rel = src.relative_to(source_root)
        dest = output_root / rel.with_suffix(".webp")

        if skip_existing and dest.is_file():
            report.skipped_existing += 1
            report.converted_bytes += dest.stat().st_size
            continue

        if dry_run:
            report.converted += 1  # would convert
            if estimate_budget > 0:
                try:
                    result = convert_to_webp(src, settings=cfg)
                    estimated_in += original_size
                    estimated_out += result.output_size_bytes
                    estimated_n += 1
                    estimate_budget -= 1
                except ImageProcessingError as error:
                    report.failed += 1
                    report.failures.append({"path": str(src), "error": str(error)[:300]})
            continue

        try:
            result = convert_to_webp(src, settings=cfg)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(result.content)
            report.converted += 1
            report.converted_bytes += result.output_size_bytes
            emit(f"converted {rel} -> {dest.relative_to(output_root)}")
        except ImageProcessingError as error:
            report.failed += 1
            report.failures.append({"path": str(src), "error": str(error)[:300]})
            emit(f"FAILED {rel}: {error}")

    if dry_run and estimated_n > 0 and estimated_in > 0:
        ratio = estimated_out / float(estimated_in)
        # Project from sample onto files that would be newly converted.
        projected = int(report.original_bytes * ratio)
        report.converted_bytes = projected
        report.notes.append(
            f"Size projection from {estimated_n} sample encode(s); "
            f"sample_ratio={ratio:.4f}."
        )

    report.per_class_counts = dict(sorted(class_counts.items()))
    report.per_format_counts = dict(sorted(format_counts.items()))
    report.finished_at = datetime.now(timezone.utc).isoformat()
    return report


def write_report(report: BulkConversionReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path
