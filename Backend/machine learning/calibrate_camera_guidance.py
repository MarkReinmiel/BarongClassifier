"""Measure the training photos with the same checks the phone camera guide uses.

The camera guide (Frontend/src/js/cameraGuidance.js) compares each live frame with
these numbers, so its "good distance" range matches the texture scale the CNN was
trained on. It does not measure physical distance.

Run from the project root:

    python "Backend/machine learning/calibrate_camera_guidance.py"

It prints per-class statistics, a zoom check (the same photos simulated closer and
farther), and suggested threshold values for CAMERA_GUIDANCE_CONFIG. Nothing is
modified.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT / "Backend" / "dataset"
CLASSES = ["cocoon", "jusi", "pina"]

# Must match CAMERA_GUIDANCE_CONFIG.ANALYSIS_SIZE / GRID_CELLS / GLARE_LEVEL in JS.
ANALYSIS_SIZE = 224
GRID_CELLS = 4
GLARE_LEVEL = 250


def luma(image: Image.Image) -> np.ndarray:
    """Same 224x224 view as cameraGuidance.js: halve in steps, then a final resize."""
    image = image.convert("RGB")
    width, height = image.size
    while width > 2 * ANALYSIS_SIZE or height > 2 * ANALYSIS_SIZE:
        width = max(ANALYSIS_SIZE, round(width / 2))
        height = max(ANALYSIS_SIZE, round(height / 2))
        image = image.resize((width, height), Image.Resampling.BOX)
    rgb = np.asarray(
        image.resize((ANALYSIS_SIZE, ANALYSIS_SIZE), Image.Resampling.BILINEAR),
        dtype=np.float32,
    )
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def gradient_map(y: np.ndarray) -> np.ndarray:
    return np.abs(y[:-1, 1:] - y[:-1, :-1]) + np.abs(y[1:, :-1] - y[:-1, :-1])


def measure(y: np.ndarray) -> dict:
    g = gradient_map(y)
    texture = float(g.mean())

    half = y.reshape(ANALYSIS_SIZE // 2, 2, ANALYSIS_SIZE // 2, 2).mean(axis=(1, 3))
    coarse = float(gradient_map(half).mean())
    scale = coarse / (2 * texture) if texture > 1e-6 else 0.0

    lap = (
        4 * y[1:-1, 1:-1] - y[:-2, 1:-1] - y[2:, 1:-1] - y[1:-1, :-2] - y[1:-1, 2:]
    )

    size = g.shape[0]
    cells = []
    for row in range(GRID_CELLS):
        for col in range(GRID_CELLS):
            y0, y1 = row * size // GRID_CELLS, (row + 1) * size // GRID_CELLS
            x0, x1 = col * size // GRID_CELLS, (col + 1) * size // GRID_CELLS
            cells.append(float(g[y0:y1, x0:x1].mean()))

    return {
        "brightness": float(y.mean()),
        "glare": float((y >= GLARE_LEVEL).mean()),
        "texture": texture,
        "scale": scale,
        "sharpness": float(lap.var()),
        "min_cell_texture": min(cells),
    }


def zoomed(image: Image.Image, factor: float) -> Image.Image:
    """Simulate the same textile photographed closer (>1) or farther (<1)."""
    width, height = image.size
    if factor >= 1:
        crop_w, crop_h = int(width / factor), int(height / factor)
        left, top = (width - crop_w) // 2, (height - crop_h) // 2
        return image.crop((left, top, left + crop_w, top + crop_h))
    tiles = int(np.ceil(1 / factor))
    small = image.resize((int(width * factor), int(height * factor)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (small.width * tiles, small.height * tiles))
    for row in range(tiles):
        for col in range(tiles):
            canvas.paste(small, (col * small.width, row * small.height))
    return canvas.crop((0, 0, width, height))


def percentiles(values: list[float]) -> str:
    p = np.percentile(values, [1, 5, 50, 95, 99])
    return "  ".join(f"p{q}={v:8.3f}" for q, v in zip([1, 5, 50, 95, 99], p))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    rows: dict[str, list[dict]] = {name: [] for name in CLASSES}
    zoom_rows: dict[float, list[float]] = {0.5: [], 0.7: [], 1.0: [], 1.4: [], 2.0: []}

    for class_name in CLASSES:
        paths = sorted(
            p
            for p in (DATASET_DIR / class_name).iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )
        for index, path in enumerate(paths):
            with Image.open(path) as image:
                image = image.convert("RGB")
                rows[class_name].append(measure(luma(image)))
                if index % 5 == 0:
                    for factor in zoom_rows:
                        zoom_rows[factor].append(measure(luma(zoomed(image, factor)))["scale"])
        print(f"Measured {len(paths)} {class_name} photos", flush=True)

    everything = [row for class_rows in rows.values() for row in class_rows]
    for metric in ["scale", "sharpness", "brightness", "glare", "texture", "min_cell_texture"]:
        print(f"\n{metric}")
        for class_name in CLASSES:
            print(f"  {class_name:7s} {percentiles([r[metric] for r in rows[class_name]])}")
        print(f"  {'all':7s} {percentiles([r[metric] for r in everything])}")

    print("\nscale when the same photos are simulated closer/farther (median)")
    for factor, values in zoom_rows.items():
        label = "closer" if factor > 1 else ("farther" if factor < 1 else "as trained")
        print(f"  zoom {factor:>3}x ({label:10s}) scale={np.median(values):.3f}")

    scale = [r["scale"] for r in everything]
    sharp = [r["sharpness"] for r in everything]
    bright = [r["brightness"] for r in everything]
    good_min = np.percentile(scale, 1)
    good_max = min(np.percentile(scale, 99), 0.95)
    print("\nSuggested CAMERA_GUIDANCE_CONFIG values (almost every training photo is 'good'):")
    print(f"  SCALE_ADJUST_MIN: {good_min - 0.06:.2f}")
    print(f"  SCALE_GOOD_MIN: {good_min:.2f}")
    print(f"  SCALE_GOOD_MAX: {good_max:.2f}")
    print(f"  SCALE_ADJUST_MAX: {min(good_max + 0.08, 0.99):.2f}")
    # Live video frames are softer than the still photos measured here.
    print(f"  SHARPNESS_GOOD_MIN: {np.percentile(sharp, 1) * 0.4:.0f}")
    print(f"  SHARPNESS_MIN: {np.percentile(sharp, 1) * 0.2:.0f}")
    print(f"  dataset brightness p1..p99: {np.percentile(bright, 1):.0f} .. {np.percentile(bright, 99):.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
