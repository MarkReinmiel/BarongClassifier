"""Copy provisional variant model into Customer and Owner model dirs.

Does not replace the main 3-class model.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "ml" / "models" / "variant" / "active"
CUSTOMER = ROOT / "Customer" / "models"
OWNER = ROOT / "Owner" / "models"
BACKEND = ROOT / "Backend" / "machine learning" / "artifacts"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def copy_pair(dest_dir: Path) -> dict:
    dest_dir.mkdir(parents=True, exist_ok=True)
    model_src = SRC / "barong_pina_variant.keras"
    labels_src = SRC / "labels.json"
    if not model_src.is_file() or not labels_src.is_file():
        raise FileNotFoundError(f"Missing variant artifacts in {SRC}")
    model_dst = dest_dir / "barong_pina_variant.keras"
    labels_dst = dest_dir / "barong_pina_variant_labels.json"
    shutil.copy2(model_src, model_dst)
    shutil.copy2(labels_src, labels_dst)
    return {
        "model": str(model_dst),
        "labels": str(labels_dst),
        "sha256": sha256(model_dst),
    }


def main() -> int:
    labels = json.loads((SRC / "labels.json").read_text(encoding="utf-8"))
    results = {
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "version": labels.get("version"),
        "threshold": labels.get("acceptance_threshold"),
        "customer": copy_pair(CUSTOMER),
        "owner": copy_pair(OWNER),
    }
    if BACKEND.is_dir():
        results["backend"] = copy_pair(BACKEND)
    log = SRC / "deploy_log.json"
    log.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
