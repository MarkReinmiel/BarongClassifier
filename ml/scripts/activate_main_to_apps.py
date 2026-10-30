"""Copy ml/models/active main classifier into Customer + Owner (after explicit approval).

Does not delete backups. Overwrites app model files only after candidate exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = ROOT / "ml" / "models" / "active"
SRC_MODEL = ACTIVE / "main_classifier.keras"
SRC_LABELS = ACTIVE / "labels.json"


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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm",
        required=True,
        help='Must be exactly: DEPLOY_MAIN_TO_CUSTOMER_AND_OWNER',
    )
    args = parser.parse_args()
    if args.confirm != "DEPLOY_MAIN_TO_CUSTOMER_AND_OWNER":
        raise SystemExit("Refusing to deploy without --confirm DEPLOY_MAIN_TO_CUSTOMER_AND_OWNER")

    if not SRC_MODEL.is_file() or not SRC_LABELS.is_file():
        raise SystemExit(f"Missing candidate under {ACTIVE}")

    targets = [
        (
            ROOT / "Frontend" / "src" / "customer" / "models" / "barong_model.keras",
            ROOT / "Frontend" / "src" / "customer" / "models" / "labels.json",
        ),
        (
            ROOT / "Frontend" / "src" / "owner" / "models" / "barong_model.keras",
            ROOT / "Frontend" / "src" / "owner" / "models" / "labels.json",
        ),
    ]
    log = {
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "source_model_sha256": sha256(SRC_MODEL),
        "targets": [],
    }
    for model_dest, labels_dest in targets:
        model_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC_MODEL, model_dest)
        shutil.copy2(SRC_LABELS, labels_dest)
        log["targets"].append(
            {
                "model": str(model_dest),
                "labels": str(labels_dest),
                "model_sha256": sha256(model_dest),
            }
        )
        print(f"deployed -> {model_dest}")

    # Optional: keep Backend artifact in sync for classify_server users.
    backend_model = ROOT / "Backend" / "machine learning" / "artifacts" / "barong_mobilenetv2.keras"
    backend_labels = ROOT / "Backend" / "machine learning" / "artifacts" / "labels.json"
    if backend_model.parent.is_dir():
        shutil.copy2(SRC_MODEL, backend_model)
        shutil.copy2(SRC_LABELS, backend_labels)
        log["targets"].append(
            {
                "model": str(backend_model),
                "labels": str(backend_labels),
                "model_sha256": sha256(backend_model),
            }
        )
        print(f"deployed -> {backend_model}")

    metrics_path = ACTIVE / "metrics.json"
    if metrics_path.is_file():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        metrics["deployed_to_apps"] = True
        metrics["deployed_at"] = log["deployed_at"]
        metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    out = ACTIVE / "deploy_log.json"
    out.write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
