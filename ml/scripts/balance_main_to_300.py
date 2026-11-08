"""Pad each main_classifier class to exactly 300 images.

Uses unique originals already prepared under ml/data/main_classifier/{class}.
Adds _bal{N} copies when a class is short; trims surplus when over TARGET.
Never moves images across textile classes.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "ml" / "data" / "main_classifier"
CLASSES = ("cocoon", "jusi", "pina")
TARGET = 300
IMG_EXT = {".jpg", ".jpeg", ".jpe", ".png", ".webp", ".bmp"}


def list_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT
    )


def unique_dest(folder: Path, preferred: str) -> Path:
    dest = folder / preferred
    if not dest.exists():
        return dest
    stem = Path(preferred).stem
    suffix = Path(preferred).suffix
    n = 1
    while True:
        candidate = folder / f"{stem}_x{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def pad_class(class_name: str, target: int = TARGET) -> int:
    folder = MAIN / class_name
    folder.mkdir(parents=True, exist_ok=True)
    images = list_images(folder)
    sources = [p for p in images if "_bal" not in p.stem]
    if not sources:
        sources = images
    if not sources:
        raise SystemExit(f"No images to pad for class {class_name}")

    current = len(images)
    if current >= target:
        print(f"{class_name}: already {current} (>= {target}), no pad")
        return 0

    made = 0
    i = 0
    while current + made < target:
        src = sources[i % len(sources)]
        round_n = (i // len(sources)) + 1
        dest_name = f"{src.stem}_bal{round_n}{src.suffix.lower()}"
        dest = unique_dest(folder, dest_name)
        shutil.copy2(src, dest)
        made += 1
        i += 1
        if made % 50 == 0 or current + made == target:
            print(f"{class_name}: {current + made}/{target}")
    return made


def trim_class(class_name: str, target: int = TARGET) -> int:
    folder = MAIN / class_name
    images = list_images(folder)
    if len(images) <= target:
        return 0
    # Drop balance copies first, then newest surplus names.
    bal = sorted([p for p in images if "_bal" in p.stem], key=lambda p: p.name, reverse=True)
    originals = sorted([p for p in images if "_bal" not in p.stem], key=lambda p: p.name, reverse=True)
    overflow = len(images) - target
    removed = 0
    for path in bal + originals:
        if removed >= overflow:
            break
        path.unlink(missing_ok=True)
        removed += 1
        print(f"{class_name}: removed surplus {path.name}")
    return removed


def counts() -> dict[str, int]:
    return {c: len(list_images(MAIN / c)) for c in CLASSES}


def main() -> int:
    print("=== pad / trim classes to", TARGET, "===")
    for class_name in CLASSES:
        pad_class(class_name, TARGET)
        trim_class(class_name, TARGET)

    final = counts()
    total = sum(final.values())
    print("=== final ===")
    for k, v in final.items():
        print(f"  {k}: {v}")
    print(f"  TOTAL: {total}")
    if total != TARGET * len(CLASSES) or any(v != TARGET for v in final.values()):
        print("WARNING: counts are not exactly 300 each")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
