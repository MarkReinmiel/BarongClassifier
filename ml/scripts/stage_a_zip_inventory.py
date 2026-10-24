"""Stage A helper: inventory dataset folders + ZIP archives without modifying originals.

Writes:
  ml/reports/source_inventory.json
  ml/data/staging/<safe_name>/  (extract only if --extract)

Never deletes or overwrites source ZIPs or dataset/<class> folders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "dataset"
REPORTS = ROOT / "ml" / "reports"
STAGING = ROOT / "ml" / "data" / "staging"
IMG_EXT = {".jpg", ".jpeg", ".jpe", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def safe_name(name: str) -> str:
    name = name.encode("ascii", "ignore").decode("ascii") or "archive"
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("_").lower() or "archive"


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def scan_dir(path: Path) -> dict:
    images = []
    non_images = []
    unreadable = []
    if not path.is_dir():
        return {
            "exists": False,
            "path": str(path),
            "image_count": 0,
            "images": [],
            "non_images": [],
            "unreadable": [],
        }
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        rel = str(item.relative_to(path)).replace("\\", "/")
        if item.suffix.lower() not in IMG_EXT:
            non_images.append(rel)
            continue
        meta = {"rel": rel, "bytes": item.stat().st_size}
        try:
            with Image.open(item) as im:
                im.verify()
            with Image.open(item) as im:
                meta["width"], meta["height"] = im.size
                meta["format"] = im.format
            meta["sha256"] = sha256_file(item)
            images.append(meta)
        except (UnidentifiedImageError, OSError, ValueError) as error:
            unreadable.append({"rel": rel, "error": type(error).__name__})
    return {
        "exists": True,
        "path": str(path),
        "image_count": len(images),
        "images": images,
        "non_images": non_images,
        "unreadable": unreadable,
    }


def inventory_zip(zpath: Path) -> dict:
    with zipfile.ZipFile(zpath, "r") as zf:
        names = zf.namelist()
        imgs = [n for n in names if Path(n).suffix.lower() in IMG_EXT]
        other = [n for n in names if n not in imgs and not n.endswith("/")]
        tops = sorted({n.split("/")[0] for n in names if n.strip()})
    return {
        "path": str(zpath),
        "name": zpath.name,
        "bytes": zpath.stat().st_size,
        "entries": len(names),
        "image_count": len(imgs),
        "other_files": len(other),
        "top_level": tops,
        "sample_images": imgs[:8],
        "safe_extract_name": safe_name(zpath.stem),
    }


def extract_zip(zpath: Path, dest_root: Path) -> Path:
    dest = dest_root / safe_name(zpath.stem)
    if dest.exists() and any(dest.iterdir()):
        print(f"SKIP extract (already present): {dest}")
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath, "r") as zf:
        zf.extractall(dest)
    print(f"EXTRACTED {zpath.name} -> {dest}")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract ZIPs into ml/data/staging/ (never into dataset/)",
    )
    args = parser.parse_args()
    REPORTS.mkdir(parents=True, exist_ok=True)
    STAGING.mkdir(parents=True, exist_ok=True)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "original_class_folders": {},
        "zip_archives": [],
        "staging": {},
        "notes": [
            "Originals under dataset/ were not modified.",
            "Folder names are provisional labels only.",
            "Piña Silk images require manual textile verification before training.",
        ],
    }

    for class_name in ("cocoon", "jusi", "pina"):
        report["original_class_folders"][class_name] = scan_dir(DATASET / class_name)

    for zpath in sorted(DATASET.glob("*.zip")):
        info = inventory_zip(zpath)
        report["zip_archives"].append(info)
        if args.extract:
            dest = extract_zip(zpath, STAGING)
            report["staging"][info["safe_extract_name"]] = scan_dir(dest)

    out = REPORTS / "source_inventory.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out}")

    # Quick console summary
    for name, block in report["original_class_folders"].items():
        print(f"original {name}: {block['image_count']} images, unreadable={len(block['unreadable'])}")
    for z in report["zip_archives"]:
        print(f"zip {z['name']}: {z['image_count']} images tops={z['top_level']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
