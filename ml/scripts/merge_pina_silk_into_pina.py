"""Fold Piña Silk images into the main Piña class and update the training manifest.

Copies ml/data/variant_classifier/pina_silk/* into ml/data/main_classifier/pina/
and marks matching source_manifest rows as include_in_main_train with a split.
"""

from __future__ import annotations

import csv
import hashlib
import shutil
from collections import defaultdict
from pathlib import Path

from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
SILK_DIR = ROOT / "ml" / "data" / "variant_classifier" / "pina_silk"
PINA_DIR = ROOT / "ml" / "data" / "main_classifier" / "pina"
MANIFEST = ROOT / "ml" / "reports" / "source_manifest.csv"
SEED = 42
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


def sample_id(path: Path) -> str:
    stem = path.stem
    # prepared names look like {digest12}_{original_stem}
    if "_" in stem and len(stem.split("_", 1)[0]) == 12:
        stem = stem.split("_", 1)[1]
    if stem.upper().startswith("IMG_"):
        return f"pina_silk/{stem}"
    if stem.startswith("camera-capture-"):
        return f"pina_silk/{stem}"
    return f"pina_silk/{stem}"


def main() -> int:
    if not SILK_DIR.is_dir():
        raise SystemExit(f"Missing silk folder: {SILK_DIR}")
    PINA_DIR.mkdir(parents=True, exist_ok=True)

    silk_files = sorted(
        p for p in SILK_DIR.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXT
    )
    if not silk_files:
        raise SystemExit(f"No silk images in {SILK_DIR}")

    digest_to_dest: dict[str, Path] = {}
    group_of: dict[str, str] = {}
    for src in silk_files:
        digest = sha256_file(src)
        dest = PINA_DIR / src.name
        if not dest.exists():
            shutil.copy2(src, dest)
        digest_to_dest[digest] = dest
        group_of[digest] = sample_id(src)
        print(f"pina <- {src.name}")

    groups = sorted(set(group_of.values()))
    split_of: dict[str, str] = {}
    if len(groups) < 5:
        for i, g in enumerate(groups):
            split_of[g] = ("val", "test", "train")[min(i, 2)] if len(groups) >= 3 else "train"
        if len(groups) == 1:
            split_of[groups[0]] = "train"
        elif len(groups) == 2:
            split_of[groups[0]] = "train"
            split_of[groups[1]] = "val"
    else:
        train_val, test = train_test_split(groups, test_size=0.15, random_state=SEED)
        train, val = train_test_split(
            train_val, test_size=0.15 / 0.85, random_state=SEED
        )
        for g in train:
            split_of[g] = "train"
        for g in val:
            split_of[g] = "val"
        for g in test:
            split_of[g] = "test"

    with MANIFEST.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    matched = 0
    for row in rows:
        digest = (row.get("sha256") or "").strip()
        is_silk = (
            "pia_silk" in (row.get("source_folder") or "")
            or (row.get("variant_label") or "").startswith("pina_silk")
            or digest in digest_to_dest
        )
        if not is_silk or not digest:
            continue
        dest = digest_to_dest.get(digest)
        if dest is None:
            # Fall back: match by short digest prefix in prepared filenames
            short = digest[:12]
            hits = list(PINA_DIR.glob(f"{short}_*"))
            if not hits:
                continue
            dest = hits[0]
        row["main_class"] = "pina"
        row["prepared_path"] = str(dest)
        row["include_in_main_train"] = "True"
        row["label_verification_status"] = "merged_into_pina"
        row["physical_sample_id"] = group_of.get(digest, sample_id(dest))
        row["split"] = split_of.get(row["physical_sample_id"], "train")
        row["notes"] = (
            "Former Piña Silk; folded into main Piña class (variant removed)."
        )
        row["variant_label"] = ""
        matched += 1

    # Append any silk files not already in the manifest
    known = {(r.get("sha256") or "").strip() for r in rows}
    next_id = len(rows) + 1
    for src in silk_files:
        digest = sha256_file(src)
        if digest in known:
            continue
        dest = digest_to_dest[digest]
        gid = group_of[digest]
        rows.append(
            {
                "image_id": f"img_{next_id:05d}",
                "source_folder": "variant_classifier/pina_silk",
                "source_path": str(src),
                "prepared_path": str(dest),
                "main_class": "pina",
                "variant_label": "",
                "label_verification_status": "merged_into_pina",
                "sha256": digest,
                "width": "",
                "height": "",
                "duplicate_group": digest[:12],
                "is_duplicate": "False",
                "physical_sample_id": gid,
                "split": split_of.get(gid, "train"),
                "include_in_main_train": "True",
                "notes": "Former Piña Silk; folded into main Piña class (variant removed).",
            }
        )
        next_id += 1
        matched += 1

    with MANIFEST.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    by_split: dict[str, int] = defaultdict(int)
    for row in rows:
        if str(row.get("include_in_main_train", "")).lower() in {"1", "true", "yes"}:
            if row.get("main_class") == "pina" and "Former Piña Silk" in (row.get("notes") or ""):
                by_split[row.get("split") or "?"] += 1

    print(f"Updated manifest rows for silk->pina: {matched}")
    print(f"Silk split counts: {dict(by_split)}")
    print(f"Pina folder now has {(len(list(PINA_DIR.glob('*'))))} files")
    print(f"Wrote {MANIFEST}")
    return 0


if __name__ == "__main__":
    if hasattr(__import__("sys").stdout, "reconfigure"):
        __import__("sys").stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
