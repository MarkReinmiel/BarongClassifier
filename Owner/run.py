"""Local development entry point (HTTP or HTTPS for phone camera)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app()


def _ssl_context():
    """Self-signed cert so phone browsers allow getUserMedia on the LAN IP."""
    use_https = os.getenv("USE_HTTPS", "1").lower() in {"1", "true", "yes"}
    if not use_https:
        return None, []

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "local_https"))
    from local_cert import ensure_certificate

    cert_path, key_path, addresses = ensure_certificate()
    return (str(cert_path), str(key_path)), addresses


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5001"))
    debug = os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"}
    ssl_context, addresses = _ssl_context()
    scheme = "https" if ssl_context else "http"

    print(f"Owner ready at {scheme}://127.0.0.1:{port}/", flush=True)
    if host in ("0.0.0.0", ""):
        for address in addresses or ["<LAPTOP_IP>"]:
            print(
                f"Phone ({scheme}): {scheme}://{address}:{port}/  "
                f"(if warned, Advanced > Proceed)",
                flush=True,
            )

    app.run(host=host, port=port, debug=debug, ssl_context=ssl_context)
