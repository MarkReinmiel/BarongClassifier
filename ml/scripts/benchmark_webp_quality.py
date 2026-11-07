"""Phase 3: compare WebP quality presets on a sample of dataset images.

Measures file size only by default. Optional --predict runs the production
Keras model on original vs converted bytes (does not retrain or replace weights).

  python ml/scripts/benchmark_webp_quality.py --sample 24
  python ml/scripts/benchmark_webp_quality.py --sample 24 --predict
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.image_processing.bulk import iter_images
from shared.image_processing.convert import convert_to_webp
from shared.image_processing.settings import WebPSettings


def _maybe_predict(content: bytes, model, classes: list[str], image_size: int) -> tuple[str, float]:
    import numpy as np

    with Image.open(io.BytesIO(content)) as image:
        rgb = image.convert("RGB").resize((image_size, image_size), Image.Resampling.LANCZOS)
        batch = np.asarray(rgb, dtype=np.uint8)[None, ...]
    probs = model.predict(batch, verbose=0)[0]
    best = int(probs.argmax())
    key = classes[best] if best < len(classes) else str(best)
    return key, float(probs[best])


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark WebP quality vs size.")
    parser.add_argument(
        "--source",
        type=Path,
        default=REPO_ROOT / "ml" / "data" / "main_classifier",
    )
    parser.add_argument("--sample", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--predict", action="store_true")
    parser.add_argument(
        "--model",
        type=Path,
        default=REPO_ROOT / "Frontend" / "src" / "customer" / "models" / "barong_model.keras",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPO_ROOT / "ml" / "reports" / "webp_quality_benchmark.json",
    )
    args = parser.parse_args()

    images = list(iter_images(args.source))
    if not images:
        print(f"No images under {args.source}")
        return 1
    rng = random.Random(args.seed)
    sample = images if len(images) <= args.sample else rng.sample(images, args.sample)

    presets = [
        {"name": "q85", "quality": 85, "lossless": False},
        {"name": "q90", "quality": 90, "lossless": False},
        {"name": "q95", "quality": 95, "lossless": False},
        {"name": "lossless", "quality": 100, "lossless": True},
    ]

    model = None
    classes = ["cocoon", "jusi", "pina"]
    image_size = 224
    if args.predict:
        import tensorflow as tf

        model = tf.keras.models.load_model(args.model)
        labels = args.model.with_name("labels.json")
        if labels.is_file():
            meta = json.loads(labels.read_text(encoding="utf-8"))
            classes = list(meta.get("classes") or classes)
            image_size = int(meta.get("image_size") or 224)

    rows = []
    agreement = {p["name"]: {"same": 0, "diff": 0} for p in presets}

    for path in sample:
        original = path.read_bytes()
        row = {
            "path": str(path.relative_to(args.source)),
            "original_bytes": len(original),
            "variants": {},
        }
        orig_pred = None
        if model is not None:
            orig_pred = _maybe_predict(original, model, classes, image_size)
            row["original_pred"] = {"label": orig_pred[0], "confidence": orig_pred[1]}

        for preset in presets:
            settings = WebPSettings(
                quality=int(preset["quality"]),
                lossless=bool(preset["lossless"]),
                method=6,
            )
            result = convert_to_webp(original, settings=settings)
            entry = {
                "bytes": result.output_size_bytes,
                "ratio_vs_original": round(result.output_size_bytes / max(1, len(original)), 4),
                "width": result.width,
                "height": result.height,
            }
            if model is not None and orig_pred is not None:
                pred = _maybe_predict(result.content, model, classes, image_size)
                entry["pred"] = {"label": pred[0], "confidence": pred[1]}
                same = pred[0] == orig_pred[0]
                agreement[preset["name"]]["same" if same else "diff"] += 1
                entry["label_matches_original"] = same
            row["variants"][preset["name"]] = entry
        rows.append(row)

    summary = {
        "sample_size": len(sample),
        "source": str(args.source),
        "presets": presets,
        "mean_bytes": {},
        "mean_ratio": {},
        "label_agreement": agreement if args.predict else None,
        "note": (
            "Storage/size benchmark only unless --predict. "
            "Does not retrain or change production weights."
        ),
    }
    for preset in presets:
        name = preset["name"]
        sizes = [r["variants"][name]["bytes"] for r in rows]
        ratios = [r["variants"][name]["ratio_vs_original"] for r in rows]
        summary["mean_bytes"][name] = round(sum(sizes) / len(sizes), 1)
        summary["mean_ratio"][name] = round(sum(ratios) / len(ratios), 4)

    payload = {"summary": summary, "rows": rows}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Report written: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
