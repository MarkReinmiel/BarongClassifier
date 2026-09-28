"""Classify one textile photo with the trained CNN.

Run from the project root:

    python "Backend/machine learning/predict.py" path\\to\\photo.jpg

This does not modify the photo or the web app.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from classify_server import load_keras_model

SCRIPT_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = SCRIPT_DIR / "artifacts"
DISPLAY = {"cocoon": "Cocoon", "jusi": "Jusi", "pina": "Piña"}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) != 2:
        print('Usage: python "Backend/machine learning/predict.py" <image.jpg>')
        return 1

    image_path = Path(sys.argv[1])
    if not image_path.is_file():
        print(f"Image not found: {image_path}")
        return 1

    labels_path = ARTIFACT_DIR / "labels.json"
    model_path = ARTIFACT_DIR / "barong_mobilenetv2.keras"
    if not model_path.is_file() or not labels_path.is_file():
        print("Trained model not found. Run train_cnn.py first.")
        return 1

    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    classes = labels["classes"]
    image_size = int(labels["image_size"])

    with Image.open(image_path) as image:
        resized = image.convert("RGB").resize(
            (image_size, image_size), Image.Resampling.LANCZOS
        )
        batch = np.asarray(resized, dtype=np.uint8)[None, ...]

    model = load_keras_model(model_path)
    probabilities = model.predict(batch, verbose=0)[0]
    best = int(np.argmax(probabilities))

    print(f"File: {image_path}")
    print(f"Prediction: {DISPLAY.get(classes[best], classes[best])}")
    print(f"Confidence: {probabilities[best] * 100:.1f}%")
    print("Class probabilities:")
    order = np.argsort(probabilities)[::-1]
    for index in order:
        name = DISPLAY.get(classes[index], classes[index])
        print(f"  {name}: {probabilities[index] * 100:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
