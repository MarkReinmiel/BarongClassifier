"""Local classifier for the result page.

The trained Keras model runs in Python. The website sends the uploaded photo
here and receives the textile type and confidence.

Run from the project root, and leave this window open:

    python ml/classify_server.py
"""

from __future__ import annotations

import base64
import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "ml" / "artifacts"
HOST = "127.0.0.1"
PORT = 5501
MAX_BODY_BYTES = 40 * 1024 * 1024
DISPLAY = {"cocoon": "Cocoon", "jusi": "Jusi", "pina": "Piña"}


def load_classifier():
    labels_path = ARTIFACT_DIR / "labels.json"
    model_path = ARTIFACT_DIR / "barong_mobilenetv2.keras"
    if not model_path.is_file() or not labels_path.is_file():
        raise FileNotFoundError(
            "Trained model not found. Run python ml/train_cnn.py first."
        )
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    model = tf.keras.models.load_model(model_path)
    return model, labels["classes"], int(labels["image_size"])


MODEL, CLASSES, IMAGE_SIZE = load_classifier()
PREDICT_LOCK = threading.Lock()


def decode_image(payload: str) -> np.ndarray:
    encoded = payload.split(",", 1)[1] if payload.startswith("data:") else payload
    raw = base64.b64decode(encoded, validate=False)
    with Image.open(io.BytesIO(raw)) as image:
        resized = image.convert("RGB").resize(
            (IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS
        )
        return np.asarray(resized, dtype=np.uint8)[None, ...]


def predict_image(payload: str) -> dict:
    batch = decode_image(payload)
    with PREDICT_LOCK:
        probabilities = MODEL.predict(batch, verbose=0)[0]
    best = int(np.argmax(probabilities))
    label = CLASSES[best]
    return {
        "label": label,
        "display_name": DISPLAY.get(label, label),
        "confidence": float(probabilities[best]),
        "probabilities": {
            class_name: float(probabilities[index])
            for index, class_name in enumerate(CLASSES)
        },
    }


class ClassifierHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send_json(204, {})

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] != "/health":
            self._send_json(404, {"error": "Not found"})
            return
        self._send_json(200, {"status": "ready", "classes": CLASSES})

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/predict":
            self._send_json(404, {"error": "Not found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json(400, {"error": "Image payload is missing or too large."})
            return

        try:
            message = json.loads(self.rfile.read(length).decode("utf-8"))
            image = message.get("image", "")
            if not image:
                raise ValueError("Missing image")
            result = predict_image(image)
        except (ValueError, UnidentifiedImageError, OSError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": f"Could not read that image. {exc}"})
            return

        print(
            f"{result['display_name']} {result['confidence'] * 100:.1f}%",
            flush=True,
        )
        self._send_json(200, result)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ClassifierHandler)
    print(f"Classifier ready at http://{HOST}:{PORT}/predict", flush=True)
    print("Leave this running while you use the result page.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
