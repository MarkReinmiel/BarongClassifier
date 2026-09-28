"""Serve the website over HTTPS so a phone on the same Wi-Fi can use the live camera.

Run from the project root, and leave this window open:

    python local_https/serve_frontend.py

This does the same job as `python -m http.server 5500`, but over HTTPS on port 5443.
"""

from __future__ import annotations

import argparse
import functools
import ssl
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from local_cert import ensure_certificate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 5443


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="HTTPS website server for phone testing")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    cert_path, key_path, addresses = ensure_certificate()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(PROJECT_ROOT))
    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)

    page = "/Frontend/src/pages/index.html"
    print(f"Website (laptop): https://localhost:{args.port}{page}", flush=True)
    for address in addresses:
        print(f"Website (phone):  https://{address}:{args.port}{page}", flush=True)
    print(
        "The browser will warn that the connection is not private (self-signed "
        "certificate). Tap Advanced > Proceed.",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
