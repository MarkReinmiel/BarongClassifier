"""Load ml/models/active/main_classifier.keras and score a few prepared images."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = ROOT / "ml" / "models" / "active"
MAIN = ROOT / "ml" / "data" / "main_classifier"
CLASSES = ["cocoon", "jusi", "pina"]


def predict_path(model, path: Path, image_size: int) -> tuple[str, float]:
    with Image.open(path) as im:
        arr = np.asarray(
            im.convert("RGB").resize((image_size, image_size), Image.Resampling.LANCZOS),
            dtype=np.uint8,
        )[None, ...]
    probs = model.predict(arr, verbose=0)[0]
    i = int(np.argmax(probs))
    return CLASSES[i], float(probs[i])


def main() -> int:
    model_path = ACTIVE / "main_classifier.keras"
    labels = json.loads((ACTIVE / "labels.json").read_text(encoding="utf-8"))
    image_size = int(labels.get("image_size") or 224)
    model = tf.keras.models.load_model(model_path)
    ok = 0
    total = 0
    for cls in CLASSES:
        folder = MAIN / cls
        samples = sorted(folder.glob("*"))[:3]
        for path in samples:
            if not path.is_file():
                continue
            pred, conf = predict_path(model, path, image_size)
            total += 1
            match = pred == cls
            ok += int(match)
            print(f"{path.name}: true={cls} pred={pred} conf={conf:.3f} {'OK' if match else 'MISS'}")
    print(f"smoke {ok}/{total}")
    return 0 if total and ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
