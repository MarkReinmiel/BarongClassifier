"""Extract Barong textile photos into dataset/<class>/ without altering image bytes.

Original ZIP files are opened read-only. Re-running this script does not create
a second copy of a file that is already present with the same contents.

This script only prepares the dataset. It does not train a model.
"""

from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT / "Backend" / "dataset"

# Actual archives in this project. They live inside class folders and use
# Google Drive download names, not cocoon.zip / jusi.zip / pina.zip.
ZIP_SOURCES = {
    "cocoon": ROOT
    / "barong type"
    / "cocoon"
    / "drive-download-20260921T133953Z-1-001.zip",
    "jusi": ROOT
    / "barong type"
    / "jusi"
    / "drive-download-20260921T133231Z-1-001.zip",
    "pina": ROOT
    / "barong type"
    / "pina"
    / "drive-download-20260921T133052Z-1-001.zip",
}

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_member_name(name: str) -> str | None:
    """Return a flat file name, or None if the member is nested or unsafe."""
    normalized = name.replace("\\", "/").strip()
    if not normalized or normalized.endswith("/"):
        return None
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return None
    if len(parts) != 1:
        return None
    return parts[0]


def inspect_image(data: bytes) -> tuple[str | None, tuple[int, int] | None, str | None]:
    """Decode in memory only. Returns (format, size, error)."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return image.format, image.size, None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        return None, None, f"{type(exc).__name__}: {exc}"


def describe_zip_layout(zf: zipfile.ZipFile) -> list[str]:
    parents: Counter[str] = Counter()
    for info in zf.infolist():
        if info.is_dir():
            parents[f"{info.filename} (directory entry)"] += 1
            continue
        parent = "/".join(info.filename.replace("\\", "/").split("/")[:-1])
        parents[parent or "(archive root)"] += 1
    lines = []
    for parent, count in parents.most_common():
        lines.append(f"    {count} file(s) under {parent}")
    return lines


def prepare() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    extracted_hashes: dict[str, list[str]] = defaultdict(list)
    class_reports: list[str] = []
    blocked = False

    for class_name, zip_path in ZIP_SOURCES.items():
        lines = [
            f"{class_name.capitalize() if class_name != 'pina' else 'Piña'}:",
            f"- ZIP: {zip_path.relative_to(ROOT)}",
        ]
        if not zip_path.is_file():
            lines.append("- Status: ZIP file not found. Nothing extracted.")
            class_reports.append("\n".join(lines))
            blocked = True
            continue

        dest_dir = DATASET_DIR / class_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        formats: Counter[str] = Counter()
        dimensions: Counter[str] = Counter()
        widths: list[int] = []
        heights: list[int] = []
        invalid: list[str] = []
        corrupted: list[str] = []
        skipped_existing = 0
        written = 0
        conflicts: list[str] = []
        class_hashes: dict[str, list[str]] = defaultdict(list)
        nested: list[str] = []

        with zipfile.ZipFile(zip_path) as zf:
            file_infos = [info for info in zf.infolist() if not info.is_dir()]
            lines.append(f"- Total files: {len(file_infos)}")
            layout = describe_zip_layout(zf)
            nested = [
                info.filename
                for info in file_infos
                if safe_member_name(info.filename) is None
            ]
            if nested:
                lines.append("- Nested or unsafe paths found. Extraction skipped for this ZIP.")
                lines.extend(layout)
                lines.append("- Nested entries:")
                lines.extend(f"    {name}" for name in nested[:30])
                if len(nested) > 30:
                    lines.append(f"    ... {len(nested) - 30} more")
                class_reports.append("\n".join(lines))
                blocked = True
                continue

            for info in file_infos:
                filename = safe_member_name(info.filename)
                assert filename is not None
                extension = Path(filename).suffix.lower()
                data = zf.read(info)
                digest = sha256(data)
                class_hashes[digest].append(filename)
                extracted_hashes[digest].append(f"{class_name}/{filename}")

                if extension not in IMAGE_EXTENSIONS:
                    invalid.append(f"{filename} (extension {extension or '(none)'})")
                    continue

                image_format, size, error = inspect_image(data)
                if error or image_format is None or size is None:
                    corrupted.append(f"{filename} ({error})")
                    continue

                formats[image_format] += 1
                width, height = size
                dimensions[f"{width}x{height}"] += 1
                widths.append(width)
                heights.append(height)

                destination = dest_dir / filename
                if destination.exists():
                    existing = sha256(destination.read_bytes())
                    if existing == digest:
                        skipped_existing += 1
                        continue
                    conflicts.append(filename)
                    continue

                destination.write_bytes(data)
                written += 1

        valid_count = sum(formats.values())
        duplicate_groups = [
            names for names in class_hashes.values() if len(names) > 1
        ]
        lines.append(f"- Valid images: {valid_count}")
        lines.append(
            f"- Invalid files: {len(invalid) + len(corrupted)}"
        )
        if invalid:
            lines.append("  Non-image or unexpected extension:")
            lines.extend(f"    {item}" for item in invalid)
        if corrupted:
            lines.append("  Corrupted or unreadable:")
            lines.extend(f"    {item}" for item in corrupted)
        if not invalid and not corrupted:
            lines.append("  None")
        lines.append(
            "- Image formats: "
            + (", ".join(f"{fmt} ({count})" for fmt, count in formats.most_common()) or "none")
        )
        if dimensions:
            common = ", ".join(
                f"{size} ({count})" for size, count in dimensions.most_common(5)
            )
            lines.append(f"- Common dimensions: {common}")
            lines.append(
                f"- Dimension range: width {min(widths)}-{max(widths)}, "
                f"height {min(heights)}-{max(heights)}"
            )
        else:
            lines.append("- Common dimensions: none")
        lines.append(f"- Archive layout: {layout[0].strip() if layout else 'empty'}")
        lines.append(
            f"- Exact duplicate groups inside this class: {len(duplicate_groups)}"
        )
        for names in duplicate_groups:
            lines.append(f"    {', '.join(names)}")
        lines.append(
            f"- Wrote {written} new file(s); left {skipped_existing} existing matching file(s) unchanged"
        )
        if conflicts:
            lines.append(
                "- Name conflicts (existing file differs, left untouched): "
                + ", ".join(conflicts)
            )
        class_reports.append("\n".join(lines))

    cross_class = [
        (digest, names)
        for digest, names in extracted_hashes.items()
        if len({name.split('/', 1)[0] for name in names}) > 1
    ]

    print("BarongClassifier dataset preparation")
    print(f"Dataset directory: {DATASET_DIR}")
    print()
    print("\n\n".join(class_reports))
    print()
    print(f"Cross-class exact duplicates: {len(cross_class)}")
    for _digest, names in cross_class:
        print(f"  {', '.join(names)}")
    if blocked:
        print()
        print("Extraction stopped where nested paths were found. No files were flattened.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(prepare())
