"""Copy current Customer/Owner working models into ml/models/backups/ (never delete)."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKUP_ROOT = ROOT / "ml" / "models" / "backups"
TARGETS = [
    ROOT / "Frontend" / "src" / "customer" / "models" / "barong_model.keras",
    ROOT / "Frontend" / "src" / "customer" / "models" / "labels.json",
    ROOT / "Frontend" / "src" / "owner" / "models" / "barong_model.keras",
    ROOT / "Frontend" / "src" / "owner" / "models" / "labels.json",
    ROOT / "Backend" / "machine learning" / "artifacts" / "barong_mobilenetv2.keras",
    ROOT / "Backend" / "machine learning" / "artifacts" / "labels.json",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            b = fh.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_ROOT / f"pre_retrain_{stamp}"
    dest.mkdir(parents=True, exist_ok=False)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "files": []}
    for src in TARGETS:
        if not src.is_file():
            manifest["files"].append({"src": str(src), "status": "missing"})
            continue
        out = dest / src.name
        # Disambiguate Customer vs Owner same filenames.
        parts_l = {p.lower() for p in src.parts}
        if "customer" in parts_l:
            out = dest / f"customer_{src.name}"
        elif "owner" in parts_l:
            out = dest / f"owner_{src.name}"
        elif "artifacts" in src.parts:
            out = dest / f"backend_{src.name}"
        shutil.copy2(src, out)
        manifest["files"].append(
            {
                "src": str(src),
                "backup": str(out),
                "sha256": sha256(out),
                "bytes": out.stat().st_size,
                "status": "copied",
            }
        )
        print(f"backed up {src} -> {out}")
    (dest / "backup_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Backup folder: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
