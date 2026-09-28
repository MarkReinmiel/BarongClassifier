"""Local classifier for the result page.

The trained Keras model runs in Python. The website sends the uploaded photo
here and receives the textile type and confidence.

Run from the project root, and leave this window open:

    python "Backend/machine learning/classify_server.py"

To test from a phone on the same Wi-Fi, listen on the local network too:

    python "Backend/machine learning/classify_server.py" --host 0.0.0.0
"""

from __future__ import annotations

import argparse
import base64
import binascii
import io
import ipaddress
import json
import os
import socket
import ssl
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from PIL import Image, UnidentifiedImageError

SCRIPT_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = SCRIPT_DIR / "artifacts"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5501
DEFAULT_HTTPS_PORT = 5502
MAX_BODY_BYTES = 40 * 1024 * 1024
DISPLAY = {"cocoon": "Cocoon", "jusi": "Jusi", "pina": "Piña"}


def load_classifier():
    labels_path = ARTIFACT_DIR / "labels.json"
    model_path = ARTIFACT_DIR / "barong_mobilenetv2.keras"
    if not model_path.is_file() or not labels_path.is_file():
        raise FileNotFoundError(
            "Trained model not found at "
            f"{model_path}. Expected files under Backend/machine learning/artifacts/."
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


def is_local_origin(origin: str) -> bool:
    """Allow the website only when it is opened from this laptop or the home network."""
    try:
        host = urlsplit(origin).hostname or ""
    except ValueError:
        return False
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def lan_addresses() -> list[str]:
    addresses = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            # UDP connect sends no packets; it only picks the outgoing interface.
            probe.connect(("8.8.8.8", 80))
            addresses.add(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass
    return sorted(
        address
        for address in addresses
        if ipaddress.ip_address(address).is_private
        and not ipaddress.ip_address(address).is_loopback
    )


class ClassifierHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin and is_local_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            if self.headers.get("Access-Control-Request-Private-Network") == "true":
                self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Vary", "Origin")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] != "/health":
            self._send_json(404, {"error": "Not found"})
            return
        self._send_json(200, {"status": "ok", "classes": CLASSES})

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/predict":
            self._send_json(404, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            self._send_json(400, {"error": "No image was received."})
            return
        if length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "That image is too large. Try a smaller photo."})
            return

        try:
            message = json.loads(self.rfile.read(length).decode("utf-8"))
            image = message.get("image", "") if isinstance(message, dict) else ""
            if not image:
                raise ValueError("Missing image")
            result = predict_image(image)
        except UnidentifiedImageError:
            self._send_json(
                415,
                {"error": "Unsupported image format. Use a JPG or PNG photo."},
            )
            return
        except (ValueError, OSError, binascii.Error, UnicodeDecodeError):
            self._send_json(400, {"error": "Could not read that image. Try another photo."})
            return
        except Exception:
            traceback.print_exc()
            self._send_json(
                500,
                {"error": "The classifier could not process this image. Please try again."},
            )
            return

        print(
            f"{result['display_name']} {result['confidence'] * 100:.1f}% "
            f"(from {self.client_address[0]})",
            flush=True,
        )
        self._send_json(200, result)

    def log_message(self, format: str, *args) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Barong textile classifier server")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Use 0.0.0.0 to allow phones on the same Wi-Fi (default: 127.0.0.1)",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--https",
        action="store_true",
        help="Also listen over HTTPS (for the phone camera) using local_https/ certificates",
    )
    parser.add_argument("--https-port", type=int, default=DEFAULT_HTTPS_PORT)
    return parser.parse_args()


def start_https_server(host: str, port: int) -> None:
    sys.path.insert(0, str(SCRIPT_DIR.parents[1] / "local_https"))
    from local_cert import ensure_certificate

    cert_path, key_path, addresses = ensure_certificate()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)

    https_server = ThreadingHTTPServer((host, port), ClassifierHandler)
    https_server.socket = context.wrap_socket(https_server.socket, server_side=True)
    threading.Thread(target=https_server.serve_forever, daemon=True).start()

    print(f"HTTPS classifier ready at https://localhost:{port}/predict", flush=True)
    if host in ("0.0.0.0", ""):
        for address in addresses:
            print(
                f"Phone HTTPS check (open once, tap Advanced > Proceed): "
                f"https://{address}:{port}/health",
                flush=True,
            )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ClassifierHandler)
    print(f"Classifier ready at http://127.0.0.1:{args.port}/predict", flush=True)
    if args.host in ("0.0.0.0", ""):
        for address in lan_addresses():
            print(
                f"Phone check (same Wi-Fi): http://{address}:{args.port}/health",
                flush=True,
            )
    else:
        print(
            "Only this laptop can connect. Add --host 0.0.0.0 to test from a phone.",
            flush=True,
        )
    if args.https:
        start_https_server(args.host, args.https_port)
    print("Leave this running while you use the result page.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
