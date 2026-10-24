"""Verify Cloudinary credentials from Owner/.env without printing secrets.

Usage (from Owner/):
  .venv\\Scripts\\python.exe ..\\ml\\scripts\\verify_cloudinary.py
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from dotenv import dotenv_values
from PIL import Image


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    env = dotenv_values(root / "Owner" / ".env")
    cloud = (env.get("CLOUDINARY_CLOUD_NAME") or "").strip().strip('"').strip("'")
    key = (env.get("CLOUDINARY_API_KEY") or "").strip().strip('"').strip("'")
    secret = (env.get("CLOUDINARY_API_SECRET") or "").strip().strip('"').strip("'")
    print("cloud_name_set", bool(cloud), "key_set", bool(key), "secret_set", bool(secret))
    print("lengths", len(cloud), len(key), len(secret))
    if not (cloud and key and secret):
        print("RESULT FAIL missing_env")
        return 1
    import cloudinary
    import cloudinary.api
    import cloudinary.uploader

    cloudinary.config(cloud_name=cloud, api_key=key, api_secret=secret, secure=True)
    try:
        status = cloudinary.api.ping().get("status")
        print("ping", status)
    except Exception as e:
        print("RESULT FAIL ping", type(e).__name__, str(e)[:160])
        print(
            "Fix: Cloudinary Dashboard > Settings > API Keys > "
            "copy Cloud name, API Key, and API Secret into Owner/.env and Customer/.env (same trio)."
        )
        return 2
    buf = BytesIO()
    Image.new("RGB", (48, 48), (210, 190, 160)).save(buf, format="JPEG")
    buf.seek(0)
    try:
        r = cloudinary.uploader.upload(
            buf,
            public_id="barong/classifications/_verify/credential_check",
            overwrite=True,
        )
        url = r.get("secure_url") or ""
        print("upload_ok", url.startswith("https://"))
        print("public_id", r.get("public_id"))
        print("url_prefix", "/".join(url.split("/")[:4]) if url else "")
        print("RESULT OK")
        return 0
    except Exception as e:
        print("RESULT FAIL upload", type(e).__name__, str(e)[:160])
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
