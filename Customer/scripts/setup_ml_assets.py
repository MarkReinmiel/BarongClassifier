"""Copy the trained model and link the training dataset into Customer/.

Run from the Customer folder or repo root:

    python scripts/setup_ml_assets.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

CUSTOMER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CUSTOMER_ROOT.parent
SRC_ARTIFACTS = REPO_ROOT / "Backend" / "machine learning" / "artifacts"
SRC_DATASET = REPO_ROOT / "dataset"
MODELS_DIR = CUSTOMER_ROOT / "models"
DATASETS_DIR = CUSTOMER_ROOT / "datasets"
CLASSES = ("cocoon", "jusi", "pina")


def _link_or_copy(src: Path, dest: Path) -> str:
    if dest.exists() or dest.is_symlink():
        if dest.is_dir() and not dest.is_symlink():
            # Junctions on Windows report as directories; remove via rmdir.
            try:
                dest.rmdir()
            except OSError:
                shutil.rmtree(dest)
        else:
            dest.unlink(missing_ok=True)

    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dest), str(src)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return "junction"
        print(result.stderr or result.stdout, file=sys.stderr)

    try:
        dest.symlink_to(src, target_is_directory=True)
        return "symlink"
    except OSError:
        shutil.copytree(src, dest)
        return "copy"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    model_src = SRC_ARTIFACTS / "barong_mobilenetv2.keras"
    labels_src = SRC_ARTIFACTS / "labels.json"
    metrics_src = SRC_ARTIFACTS / "metrics.json"
    if not model_src.is_file() or not labels_src.is_file():
        print(f"Missing Backend artifacts under {SRC_ARTIFACTS}")
        print("Train first: python \"Backend/machine learning/train_cnn.py\"")
        return 1

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(model_src, MODELS_DIR / "barong_model.keras")
    shutil.copy2(labels_src, MODELS_DIR / "labels.json")
    print(f"Copied model -> {MODELS_DIR / 'barong_model.keras'}")
    print(f"Copied labels -> {MODELS_DIR / 'labels.json'}")
    if metrics_src.is_file():
        shutil.copy2(metrics_src, MODELS_DIR / "metrics.json")
        print(f"Copied metrics -> {MODELS_DIR / 'metrics.json'}")


    if not SRC_DATASET.is_dir():
        print(f"Missing dataset folder: {SRC_DATASET}")
        return 1

    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    for class_name in CLASSES:
        src = SRC_DATASET / class_name
        dest = DATASETS_DIR / class_name
        if not src.is_dir():
            print(f"Missing class folder: {src}")
            return 1
        mode = _link_or_copy(src, dest)
        count = sum(1 for p in dest.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
        print(f"{class_name}: {count} images ({mode} -> {src})")

    print()
    print("Next:")
    print("  python -m pip install -r requirements-ml.txt")
    print("  python scripts/train_cnn.py          # optional retrain")
    print("  flask run --host 127.0.0.1 --port 5000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
