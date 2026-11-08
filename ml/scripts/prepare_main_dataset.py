"""Stage B: prepare main 3-class dataset without modifying originals.

Rules (user decisions 2026-10-24, updated 2026-11-08):
- pia_silk / pina_silk: removed from training data (not folded into Piña).
- Expansion packs stay within their textile only (never cross-labeled):
  cocoon_2/cocoon_3 → cocoon; jusi_2/jusi_3 → jusi; pina_2/pina_2.1/pina_3 → pina.
- Exact duplicates (sha256) excluded from prepared training copies (recorded in manifest).
- Originals under dataset/ and staging ZIPs are never deleted/renamed.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "Backend" / "dataset"
STAGING = ROOT / "ml" / "data" / "staging"
MAIN = ROOT / "ml" / "data" / "main_classifier"
REPORTS = ROOT / "ml" / "reports"
IMG_EXT = {".jpg", ".jpeg", ".jpe", ".png", ".webp", ".bmp"}
CLASSES = ["cocoon", "jusi", "pina"]
SEED = 42
GROUP_PATTERN = re.compile(r"^(IMG_\d{8}_\d{6})(?:_\d+)?$", re.IGNORECASE)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def capture_group(path: Path, class_name: str) -> str:
    match = GROUP_PATTERN.match(path.stem)
    if match:
        return f"{class_name}/{match.group(1)}"
    # camera-capture timestamps often encode one shot; keep stem so multi-angle
    # of unknown samples are not falsely merged across different fabrics.
    return f"{class_name}/{path.stem}"


def iter_images(folder: Path):
    if not folder.is_dir():
        return
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMG_EXT:
            yield path


def probe(path: Path) -> dict:
    meta = {"width": "", "height": "", "format": "", "readable": False, "error": ""}
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            meta["width"], meta["height"] = im.size
            meta["format"] = im.format or ""
            meta["readable"] = True
    except (UnidentifiedImageError, OSError, ValueError) as error:
        meta["error"] = type(error).__name__
    return meta


def collect_sources() -> list[dict]:
    """Build candidate rows with provisional main_class assignments."""
    # Priority within each textile: *3 packs first, then originals, then older expansions.
    sources: list[tuple[str, Path, str, str]] = [
        ("staging/cocoon_3", STAGING / "cocoon_3", "cocoon", "user_accepted_expansion_v3"),
        ("staging/jusi_3", STAGING / "jusi_3", "jusi", "user_accepted_expansion_v3"),
        ("staging/pina_3", STAGING / "pina_3", "pina", "user_accepted_expansion_v3"),
        ("Backend/dataset/cocoon", DATASET / "cocoon", "cocoon", "original_verified_folder"),
        ("Backend/dataset/jusi", DATASET / "jusi", "jusi", "original_verified_folder"),
        ("Backend/dataset/pina", DATASET / "pina", "pina", "original_verified_folder"),
        ("staging/cocoon_2", STAGING / "cocoon_2", "cocoon", "user_accepted_expansion"),
        ("staging/jusi_2", STAGING / "jusi_2", "jusi", "user_accepted_expansion"),
        ("staging/pina_2", STAGING / "pina_2", "pina", "user_accepted_as_pina"),
        ("staging/pina_2_1", STAGING / "pina_2_1", "pina", "user_accepted_as_pina"),
    ]
    rows = []
    for source_folder, root, main_class, status in sources:
        for path in iter_images(root):
            info = probe(path)
            digest = sha256_file(path) if info["readable"] else ""
            rows.append(
                {
                    "source_folder": source_folder,
                    "source_path": str(path),
                    "main_class": main_class,
                    "variant_label": "",
                    "label_verification_status": status,
                    "sha256": digest,
                    "width": info["width"],
                    "height": info["height"],
                    "readable": info["readable"],
                    "notes": info["error"],
                    "include_in_main_train": info["readable"],
                }
            )
    return rows


def mark_duplicates(rows: list[dict]) -> None:
    first_of: dict[str, str] = {}
    for row in rows:
        digest = row.get("sha256") or ""
        if not digest:
            row["duplicate_group"] = ""
            continue
        if digest not in first_of:
            first_of[digest] = row["source_path"]
            row["duplicate_group"] = digest[:12]
            row["is_duplicate"] = False
        else:
            row["duplicate_group"] = digest[:12]
            row["is_duplicate"] = True
            row["include_in_main_train"] = False
            row["notes"] = (
                (row.get("notes") + "; ") if row.get("notes") else ""
            ) + f"exact duplicate of {first_of[digest]}"


def clear_prepared_classes() -> None:
    """Wipe prepared class folders so old balance copies / retired packs do not linger."""
    for class_name in CLASSES:
        folder = MAIN / class_name
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)


def prepare_copies(rows: list[dict]) -> None:
    clear_prepared_classes()

    used_names: set[str] = set()
    for index, row in enumerate(rows, start=1):
        row["image_id"] = f"img_{index:05d}"
        row["prepared_path"] = ""
        row["physical_sample_id"] = "unknown"
        row["split"] = ""
        if not row.get("include_in_main_train"):
            continue
        src = Path(row["source_path"])
        digest = row["sha256"][:12] or row["image_id"]
        dest_name = f"{digest}_{src.stem}{src.suffix.lower()}"
        # Avoid collisions across stems.
        if dest_name in used_names:
            dest_name = f"{digest}_{row['image_id']}{src.suffix.lower()}"
        used_names.add(dest_name)
        dest = MAIN / row["main_class"] / dest_name
        if not dest.exists():
            shutil.copy2(src, dest)
        row["prepared_path"] = str(dest)
        row["physical_sample_id"] = capture_group(src, row["main_class"])


def assign_splits(rows: list[dict]) -> None:
    trainable = [r for r in rows if r.get("include_in_main_train") and r.get("prepared_path")]
    groups_by_class: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()
    for row in trainable:
        gid = row["physical_sample_id"]
        if gid in seen:
            continue
        seen.add(gid)
        groups_by_class[row["main_class"]].append(gid)

    split_of: dict[str, str] = {}
    for class_name, groups in groups_by_class.items():
        groups = sorted(groups)
        if len(groups) < 5:
            # Too few groups: put all in train and document limitation.
            for g in groups:
                split_of[g] = "train"
            continue
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

    for row in trainable:
        row["split"] = split_of.get(row["physical_sample_id"], "train")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    MAIN.mkdir(parents=True, exist_ok=True)

    main_rows = collect_sources()
    mark_duplicates(main_rows)
    prepare_copies(main_rows)
    assign_splits(main_rows)

    fields = [
        "image_id",
        "source_folder",
        "source_path",
        "prepared_path",
        "main_class",
        "variant_label",
        "label_verification_status",
        "sha256",
        "width",
        "height",
        "duplicate_group",
        "is_duplicate",
        "physical_sample_id",
        "split",
        "include_in_main_train",
        "notes",
    ]
    write_csv(REPORTS / "source_manifest.csv", main_rows, fields)

    counts = Counter()
    groups = Counter()
    for row in main_rows:
        if row.get("include_in_main_train") and row.get("prepared_path"):
            counts[(row["split"], row["main_class"])] += 1
            groups[(row["split"], row["main_class"], row["physical_sample_id"])] += 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "main_candidates": len(main_rows),
        "main_included": sum(1 for r in main_rows if r.get("include_in_main_train")),
        "main_excluded_duplicates_or_unreadable": sum(
            1 for r in main_rows if not r.get("include_in_main_train")
        ),
        "prepared_class_counts": {
            c: sum(
                1
                for r in main_rows
                if r.get("include_in_main_train") and r["main_class"] == c
            )
            for c in CLASSES
        },
        "split_image_counts": {
            f"{split}/{cls}": counts[(split, cls)]
            for split in ("train", "val", "test")
            for cls in CLASSES
        },
        "unique_groups_per_split_class": {
            f"{split}/{cls}": len(
                {gid for (s, c, gid) in groups if s == split and c == cls}
            )
            for split in ("train", "val", "test")
            for cls in CLASSES
        },
        "limitations": [
            "physical_sample_id is unknown for most images; grouping uses IMG_* stem or filename stem.",
            "Expansion packs (2 / 2.1 / 3) accepted into their own textile only; no cross-class mixing.",
            "Piña Silk dataset removed; not included in main Piña training.",
            "Exact sha256 duplicates excluded from prepared training copies.",
        ],
    }
    (REPORTS / "prepare_main_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print(f"Manifest: {REPORTS / 'source_manifest.csv'}")
    print(f"Review:   {REPORTS / 'review_required.csv'}")
    print(f"Prepared: {MAIN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
