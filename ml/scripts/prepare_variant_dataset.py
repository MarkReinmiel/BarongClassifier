"""Prepare Piña vs Piña Silk variant dataset from verified silk review + ordinary Piña.

Uses sample-grouped splits. With only 2 silk physical samples:
  - phys_silk_cam_01 → train
  - phys_silk_img_01 → test
  - no silk in val (documented limitation)

Ordinary Piña rows come from source_manifest (main train includes).
Writes:
  ml/data/variant_classifier/{pina,pina_silk}/
  ml/reports/variant_source_manifest.csv
  ml/reports/prepare_variant_summary.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "ml" / "reports"
OUT = ROOT / "ml" / "data" / "variant_classifier"
SILK_CSV = REPORTS / "pina_silk_label_review.csv"
MAIN_MANIFEST = REPORTS / "source_manifest.csv"
SEED = 42


def sha12(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()[:12]


def copy_image(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    digest = sha12(src)
    dest = dest_dir / f"{digest}_{src.name}"
    if not dest.exists():
        shutil.copy2(src, dest)
    return dest


def load_verified_silk() -> list[dict]:
    rows = []
    with SILK_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("verification_status") != "verified":
                continue
            if row.get("label") != "pina_silk":
                continue
            src = Path(row["source_path"])
            if not src.is_file():
                continue
            rows.append(
                {
                    "image_id": row["image_id"],
                    "source_path": str(src),
                    "variant_label": "pina_silk",
                    "physical_sample_id": row.get("physical_sample_id") or row["image_id"],
                    "sha256": row.get("sha256", ""),
                }
            )
    return rows


def load_ordinary_pina() -> list[dict]:
    rows = []
    with MAIN_MANIFEST.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("main_class") != "pina":
                continue
            if row.get("include_in_main_train", "").lower() not in {"1", "true", "yes"}:
                continue
            if row.get("is_duplicate", "").lower() in {"1", "true", "yes"}:
                continue
            prep = row.get("prepared_path") or row.get("source_path")
            if not prep or not Path(prep).is_file():
                continue
            rows.append(
                {
                    "image_id": row.get("image_id") or Path(prep).stem,
                    "source_path": prep,
                    "variant_label": "pina",
                    "physical_sample_id": row.get("physical_sample_id") or Path(prep).stem,
                    "sha256": row.get("sha256", ""),
                }
            )
    return rows


def assign_silk_splits(silk: list[dict]) -> None:
    for row in silk:
        sid = row["physical_sample_id"]
        if sid == "phys_silk_cam_01":
            row["split"] = "train"
        elif sid == "phys_silk_img_01":
            row["split"] = "test"
        else:
            # future samples: round-robin by sample into train/val/test
            row["split"] = "train"


def assign_pina_splits(pina: list[dict]) -> None:
    by_sample: dict[str, list[dict]] = defaultdict(list)
    for row in pina:
        by_sample[row["physical_sample_id"]].append(row)
    samples = sorted(by_sample.keys())
    rng = random.Random(SEED)
    rng.shuffle(samples)
    n = len(samples)
    n_test = max(1, int(round(n * 0.15)))
    n_val = max(1, int(round(n * 0.15)))
    test_ids = set(samples[:n_test])
    val_ids = set(samples[n_test : n_test + n_val])
    for sid, items in by_sample.items():
        if sid in test_ids:
            split = "test"
        elif sid in val_ids:
            split = "val"
        else:
            split = "train"
        for row in items:
            row["split"] = split


def main() -> int:
    random.seed(SEED)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    silk = load_verified_silk()
    pina = load_ordinary_pina()
    if not silk:
        raise SystemExit("No verified pina_silk rows. Finish Stage 1 CSV first.")
    if not pina:
        raise SystemExit("No ordinary Piña rows in source_manifest.")

    assign_silk_splits(silk)
    assign_pina_splits(pina)

    # Cap ordinary Piña roughly 2–3x silk for balance (keep sample integrity).
    silk_n = len(silk)
    target_pina = min(len(pina), max(silk_n * 3, 60))
    by_split_sample: dict[str, list[str]] = defaultdict(list)
    for row in pina:
        if row["physical_sample_id"] not in by_split_sample[row["split"]]:
            by_split_sample[row["split"]].append(row["physical_sample_id"])
    # Prefer keeping all samples that landed in val/test; subsample train images if needed.
    selected_pina = []
    train_pina = [r for r in pina if r["split"] == "train"]
    other_pina = [r for r in pina if r["split"] != "train"]
    selected_pina.extend(other_pina)
    remain = max(0, target_pina - len(selected_pina))
    rng = random.Random(SEED)
    if len(train_pina) > remain:
        # keep whole samples until near budget
        by_s: dict[str, list[dict]] = defaultdict(list)
        for r in train_pina:
            by_s[r["physical_sample_id"]].append(r)
        sids = list(by_s.keys())
        rng.shuffle(sids)
        taken = []
        for sid in sids:
            if len(taken) >= remain:
                break
            taken.extend(by_s[sid])
        selected_pina.extend(taken[:remain] if len(taken) > remain else taken)
    else:
        selected_pina.extend(train_pina)

    all_rows = silk + selected_pina
    manifest_rows = []
    for row in all_rows:
        label = row["variant_label"]
        dest = copy_image(Path(row["source_path"]), OUT / label)
        # verify readable
        try:
            with Image.open(dest) as im:
                im.verify()
            readable = True
        except Exception:
            readable = False
        manifest_rows.append(
            {
                "image_id": row["image_id"],
                "source_path": row["source_path"],
                "prepared_path": str(dest),
                "variant_label": label,
                "physical_sample_id": row["physical_sample_id"],
                "split": row["split"],
                "sha256": row.get("sha256", ""),
                "readable": readable,
                "include_in_variant_train": readable,
            }
        )

    fields = list(manifest_rows[0].keys())
    man_path = REPORTS / "variant_source_manifest.csv"
    with man_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(manifest_rows)

    def count(label=None, split=None):
        return sum(
            1
            for r in manifest_rows
            if (label is None or r["variant_label"] == label)
            and (split is None or r["split"] == split)
        )

    silk_samples = sorted({r["physical_sample_id"] for r in silk})
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_images": len(manifest_rows),
        "pina": count("pina"),
        "pina_silk": count("pina_silk"),
        "by_split": {
            s: {"pina": count("pina", s), "pina_silk": count("pina_silk", s)}
            for s in ("train", "val", "test")
        },
        "silk_physical_samples": silk_samples,
        "silk_sample_count": len(silk_samples),
        "limitations": [
            "Only 2 independent Piña Silk physical samples.",
            "No silk images in val split (EarlyStopping sees ordinary Piña only).",
            "Provisional model — retrain when ≥6–10 distinct silk textiles available.",
        ],
        "output_dir": str(OUT),
        "manifest": str(man_path),
    }
    (REPORTS / "prepare_variant_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
