"""Merge variant Piña/Piña Silk into main Piña, pad each class to 300, drop variant.

- Copies unique images from variant_classifier/pina and variant_classifier/pina_silk
  into main_classifier/pina (no variant_label).
- Pads cocoon / jusi / pina to TARGET images each by duplicating existing files
  with unique filenames (_bal{N}).
- Removes ml/data/variant_classifier after merge.
- Clears variant_label in source_manifest.csv and marks silk as pina.
"""

from __future__ import annotations

import csv
import hashlib
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "ml" / "data" / "main_classifier"
VARIANT = ROOT / "ml" / "data" / "variant_classifier"
MANIFEST = ROOT / "ml" / "reports" / "source_manifest.csv"
CLASSES = ("cocoon", "jusi", "pina")
TARGET = 300
IMG_EXT = {".jpg", ".jpeg", ".jpe", ".png", ".webp", ".bmp"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def list_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXT
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


def merge_variant_into_pina() -> int:
    pina_dir = MAIN / "pina"
    pina_dir.mkdir(parents=True, exist_ok=True)
    existing = {sha256_file(p): p for p in list_images(pina_dir)}
    added = 0
    sources = [
        VARIANT / "pina_silk",
        VARIANT / "pina",
    ]
    for src_dir in sources:
        for src in list_images(src_dir):
            digest = sha256_file(src)
            if digest in existing:
                continue
            dest = unique_dest(pina_dir, src.name)
            shutil.copy2(src, dest)
            existing[digest] = dest
            added += 1
            print(f"pina <- {src_dir.name}/{src.name}")
    return added


def pad_class(class_name: str, target: int = TARGET) -> int:
    folder = MAIN / class_name
    folder.mkdir(parents=True, exist_ok=True)
    images = list_images(folder)
    # Prefer originals (not previous balance copies) as duplication sources
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


def update_manifest() -> None:
    if not MANIFEST.is_file():
        print(f"No manifest at {MANIFEST}; skip")
        return
    with MANIFEST.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    changed = 0
    for row in rows:
        folder = (row.get("source_folder") or "").lower()
        variant = (row.get("variant_label") or "").strip().lower()
        notes = row.get("notes") or ""
        is_silk = (
            "pina_silk" in folder
            or "pia_silk" in folder
            or variant.startswith("pina_silk")
            or "silk" in variant
        )
        is_variant_pina = "variant_classifier/pina" in folder.replace("\\", "/")
        if is_silk or is_variant_pina or variant:
            row["main_class"] = "pina" if (is_silk or is_variant_pina or "pina" in variant) else row.get("main_class")
            if is_silk or is_variant_pina:
                row["main_class"] = "pina"
                row["include_in_main_train"] = "True"
            if row.get("variant_label"):
                row["variant_label"] = ""
                changed += 1
            if is_silk and "merged_into_pina" not in notes:
                row["notes"] = (
                    (notes + " " if notes else "")
                    + "Former Piña Silk; folded into main Piña (variant removed)."
                ).strip()
                row["label_verification_status"] = "merged_into_pina"
                changed += 1

    with MANIFEST.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Manifest rows updated: {changed}")


def remove_variant_tree() -> None:
    if not VARIANT.exists():
        print("variant_classifier already gone")
        return
    shutil.rmtree(VARIANT)
    print(f"Removed {VARIANT}")


def counts() -> dict[str, int]:
    return {c: len(list_images(MAIN / c)) for c in CLASSES}


def main() -> int:
    print("=== merge variant into pina ===")
    added = merge_variant_into_pina()
    print(f"Added unique images to pina: {added}")

    print("=== pad classes to", TARGET, "===")
    for class_name in CLASSES:
        pad_class(class_name, TARGET)

    print("=== update manifest / remove variant ===")
    update_manifest()
    remove_variant_tree()

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
