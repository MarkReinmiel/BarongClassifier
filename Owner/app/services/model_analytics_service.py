"""Read-only Model Analytics from real training/eval artifacts.

Does not retrain, promote, or overwrite the active CNN.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import statistics
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("owner.analytics")

OWNER_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = OWNER_ROOT.parent
CLASS_KEYS = ("cocoon", "jusi", "pina")
CLASS_LABELS = {"cocoon": "Cocoon", "jusi": "Jusi", "pina": "Piña"}


def _safe_json(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed reading JSON %s", path)
        return None


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _mb(nbytes: int | float | None) -> float | None:
    if nbytes is None:
        return None
    return round(float(nbytes) / (1024 * 1024), 2)


def _pct(value: float | None, digits: int = 1) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float(value) * 100.0, digits)


def _div(num: float, den: float) -> float | None:
    if den <= 0:
        return None
    return float(num) / float(den)


def metrics_candidates() -> list[Path]:
    return [
        REPO_ROOT / "ml" / "models" / "active" / "metrics.json",
        OWNER_ROOT / "models" / "metrics.json",
    ]


def active_model_path() -> Path | None:
    for path in (
        OWNER_ROOT / "models" / "barong_model.keras",
        REPO_ROOT / "ml" / "models" / "active" / "main_classifier.keras",
    ):
        if path.is_file():
            return path
    return None


def active_dir() -> Path:
    return REPO_ROOT / "ml" / "models" / "active"


def load_active_metrics() -> dict[str, Any]:
    for path in metrics_candidates():
        data = _safe_json(path)
        if isinstance(data, dict) and data:
            data = dict(data)
            data["_source_path"] = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            return data
    return {}


def metrics_from_confusion(
    matrix: list[list[int]], class_keys: list[str]
) -> dict[str, Any]:
    n = len(class_keys)
    if not matrix or len(matrix) != n:
        return {"per_class": [], "macro": {}, "weighted": {}, "accuracy": None, "support_total": 0}

    cm = [[int(v) for v in row] for row in matrix]
    support_total = sum(sum(row) for row in cm)
    correct = sum(cm[i][i] for i in range(n))
    accuracy = _div(correct, support_total)

    per_class = []
    macro_p = macro_r = macro_f = 0.0
    macro_n = 0
    w_p = w_r = w_f = 0.0

    for i, key in enumerate(class_keys):
        tp = cm[i][i]
        fp = sum(cm[r][i] for r in range(n)) - tp
        fn = sum(cm[i][c] for c in range(n)) - tp
        support = sum(cm[i])
        precision = _div(tp, tp + fp)
        recall = _div(tp, tp + fn)
        if precision is None or recall is None or (precision + recall) == 0:
            f1 = None
        else:
            f1 = 2.0 * precision * recall / (precision + recall)

        per_class.append(
            {
                "key": key,
                "label": CLASS_LABELS.get(key, key.title()),
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "support": support,
                "precision_pct": _pct(precision),
                "recall_pct": _pct(recall),
                "f1_pct": _pct(f1),
            }
        )
        if precision is not None and recall is not None and f1 is not None:
            macro_p += precision
            macro_r += recall
            macro_f += f1
            macro_n += 1
        if support > 0 and precision is not None and recall is not None and f1 is not None:
            w_p += precision * support
            w_r += recall * support
            w_f += f1 * support

    macro = {
        "precision": _div(macro_p, macro_n),
        "recall": _div(macro_r, macro_n),
        "f1": _div(macro_f, macro_n),
    }
    weighted = {
        "precision": _div(w_p, support_total),
        "recall": _div(w_r, support_total),
        "f1": _div(w_f, support_total),
    }
    return {
        "per_class": per_class,
        "macro": {
            **macro,
            "precision_pct": _pct(macro.get("precision")),
            "recall_pct": _pct(macro.get("recall")),
            "f1_pct": _pct(macro.get("f1")),
        },
        "weighted": {
            **weighted,
            "precision_pct": _pct(weighted.get("precision")),
            "recall_pct": _pct(weighted.get("recall")),
            "f1_pct": _pct(weighted.get("f1")),
        },
        "accuracy": accuracy,
        "accuracy_pct": _pct(accuracy),
        "support_total": support_total,
    }


def parse_classification_report(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None
    rows = {}
    averages = {}
    accuracy = None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        if parts[0].lower() == "accuracy" and len(parts) >= 2:
            try:
                accuracy = float(parts[1])
            except ValueError:
                pass
            continue
        label = parts[0]
        if label.lower() in {"macro", "weighted"} and len(parts) >= 5:
            try:
                averages[f"{label.lower()}_avg"] = {
                    "precision": float(parts[2]),
                    "recall": float(parts[3]),
                    "f1": float(parts[4]),
                    "support": int(parts[5]) if len(parts) > 5 else None,
                }
            except ValueError:
                pass
            continue
        # Class rows: "Cocoon 0.938 0.938 0.938 16" or "Piña ..."
        if len(parts) >= 5:
            name = parts[0]
            # Handle multi-token? Piña is one token in report
            try:
                precision = float(parts[1])
                recall = float(parts[2])
                f1 = float(parts[3])
                support = int(parts[4])
            except ValueError:
                continue
            key = name.lower().replace("ñ", "n").replace("piña", "pina")
            if key in CLASS_KEYS or name.lower() in {"cocoon", "jusi", "pina", "piña"}:
                if "pi" in key and "silk" not in key:
                    key = "pina" if "pina" in key or "piña" in name.lower() else key
                if name.lower().startswith("pi"):
                    key = "pina"
                rows[key] = {
                    "precision": precision,
                    "recall": recall,
                    "f1": f1,
                    "support": support,
                }
    if not rows and accuracy is None:
        return None
    return {"per_class": rows, "averages": averages, "accuracy": accuracy}


def epoch_history(metrics: dict) -> dict[str, Any]:
    hist = metrics.get("history") or {}
    if not isinstance(hist, dict):
        return {"available": False, "epochs": [], "series": {}}
    series = {}
    for key in ("accuracy", "val_accuracy", "loss", "val_loss"):
        vals = hist.get(key)
        if isinstance(vals, list) and vals:
            series[key] = [float(v) for v in vals]
    if not series:
        return {"available": False, "epochs": [], "series": {}}
    n = max(len(v) for v in series.values())
    return {
        "available": True,
        "epochs": list(range(1, n + 1)),
        "series": series,
        "epochs_completed": n,
        "best_val_accuracy": max(series["val_accuracy"]) if "val_accuracy" in series else None,
        "final_train_accuracy": series["accuracy"][-1] if "accuracy" in series else None,
        "final_val_accuracy": series["val_accuracy"][-1] if "val_accuracy" in series else None,
        "final_train_loss": series["loss"][-1] if "loss" in series else None,
        "final_val_loss": series["val_loss"][-1] if "val_loss" in series else None,
    }


def load_inference_benchmark(model_path: Path | None, version: str) -> dict[str, Any] | None:
    path = active_dir() / "inference_benchmark.json"
    data = _safe_json(path)
    if not isinstance(data, dict):
        return None
    if version and data.get("model_version") and data.get("model_version") != version:
        return None
    if model_path and data.get("model_sha256"):
        digest = _sha256_file(model_path)
        if digest and digest != data.get("model_sha256"):
            return None
    return data


def measure_inference_latency(
    *,
    samples: int = 8,
    persist: bool = True,
) -> dict[str, Any]:
    """Measure local model.predict latency only (excludes HTTP/upload)."""
    model_path = active_model_path()
    metrics = load_active_metrics()
    version = str(metrics.get("version") or "")
    cached = load_inference_benchmark(model_path, version)
    if cached:
        return {**cached, "cached": True}

    if model_path is None:
        return {
            "available": False,
            "message": "Active model file not found; inference timing unavailable.",
        }

    try:
        from app.ml.predictor import ensure_model, predict
    except Exception:
        logger.exception("Predictor import failed")
        return {"available": False, "message": "Local predictor could not be imported."}

    # Prefer real dataset images; fall back to synthetic RGB tensors via JPEG bytes.
    image_paths: list[Path] = []
    dataset = REPO_ROOT / "dataset"
    for cls in CLASS_KEYS:
        folder = dataset / cls
        if folder.is_dir():
            image_paths.extend(sorted(folder.glob("*.jpg"))[:3])
    image_paths = image_paths[:samples]

    payloads: list[bytes] = []
    if image_paths:
        for p in image_paths:
            payloads.append(p.read_bytes())
    else:
        from io import BytesIO

        from PIL import Image
        import numpy as np

        rng = np.random.default_rng(42)
        for _ in range(samples):
            arr = rng.integers(40, 220, size=(224, 224, 3), dtype=np.uint8)
            buf = BytesIO()
            Image.fromarray(arr, mode="RGB").save(buf, format="JPEG", quality=90)
            payloads.append(buf.getvalue())

    ensure_model(str(model_path), customer_root=OWNER_ROOT)
    # Warm-up (excluded from stats)
    predict(payloads[0], model_path=str(model_path), customer_root=OWNER_ROOT)

    times_ms: list[float] = []
    for blob in payloads:
        t0 = time.perf_counter()
        predict(blob, model_path=str(model_path), customer_root=OWNER_ROOT)
        times_ms.append((time.perf_counter() - t0) * 1000.0)

    times_ms.sort()
    digest = _sha256_file(model_path)
    result = {
        "available": True,
        "cached": False,
        "model_version": version,
        "model_sha256": digest,
        "n_measurements": len(times_ms),
        "avg_ms": round(statistics.fmean(times_ms), 2),
        "median_ms": round(statistics.median(times_ms), 2),
        "p95_ms": round(times_ms[max(0, math.ceil(0.95 * len(times_ms)) - 1)], 2),
        "min_ms": round(times_ms[0], 2),
        "max_ms": round(times_ms[-1], 2),
        "includes": [
            "PIL resize to model input size",
            "Keras model.predict forward pass",
        ],
        "excludes": [
            "HTTP request/response",
            "Cloudinary upload",
            "Database writes",
            "Relevance gate",
        ],
        "environment": {
            "runtime": "Owner local Flask process",
            "device": "CPU (TensorFlow local)",
            "image_size": int(metrics.get("image_size") or 224),
            "sample_source": "dataset JPEG files" if image_paths else "synthetic JPEG",
        },
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if persist:
        out = active_dir() / "inference_benchmark.json"
        try:
            out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Could not persist inference benchmark")
    return result


def list_model_versions() -> list[dict[str, Any]]:
    versions: list[dict[str, Any]] = []
    metrics = load_active_metrics()
    model_path = active_model_path()
    active_version = str(metrics.get("version") or (metrics.get("labels") or {}).get("version") or "")
    labels = _safe_json(OWNER_ROOT / "models" / "labels.json") or {}
    if not active_version and isinstance(labels, dict):
        active_version = str(labels.get("version") or "")

    if metrics or model_path:
        size = model_path.stat().st_size if model_path and model_path.is_file() else None
        cm = metrics.get("confusion_matrix") if metrics else None
        classes = list(metrics.get("classes") or CLASS_KEYS)
        scored = metrics_from_confusion(cm, classes) if cm else {}
        versions.append(
            {
                "id": active_version or "active",
                "label": active_version or "Active model",
                "architecture": metrics.get("model") or "MobileNetV2",
                "created_at": metrics.get("generated_at") or metrics.get("deployed_at"),
                "dataset": {
                    "train_images": metrics.get("train_images"),
                    "val_images": metrics.get("val_images"),
                    "test_images": metrics.get("test_images"),
                    "seed": metrics.get("seed"),
                },
                "evaluation": {
                    "accuracy": metrics.get("test_accuracy", scored.get("accuracy")),
                    "accuracy_pct": _pct(metrics.get("test_accuracy", scored.get("accuracy"))),
                    "macro_f1_pct": (scored.get("macro") or {}).get("f1_pct"),
                    "weighted_f1_pct": (scored.get("weighted") or {}).get("f1_pct"),
                    "precision_pct": (scored.get("macro") or {}).get("precision_pct"),
                    "recall_pct": (scored.get("macro") or {}).get("recall_pct"),
                    "test_images": metrics.get("test_images") or scored.get("support_total"),
                    "dataset_note": "Held-out test split from main training run",
                },
                "file_size_bytes": size,
                "file_size_mb": _mb(size),
                "format": "Keras .keras",
                "status": "Active" if model_path else "Not Available",
                "artifact": "Owner/models/barong_model.keras"
                if model_path and "Owner" in str(model_path)
                else "ml/models/active/main_classifier.keras",
                "comparable": bool(cm or metrics.get("test_accuracy") is not None),
            }
        )

    backup_dir = REPO_ROOT / "ml" / "models" / "backups" / "pre_retrain_20261024_131011"
    manifest = _safe_json(backup_dir / "backup_manifest.json")
    backup_model = backup_dir / "owner_barong_model.keras"
    if backup_model.is_file():
        size = backup_model.stat().st_size
        versions.append(
            {
                "id": "backup_pre_retrain_20261024_131011",
                "label": "Backup (pre-retrain 2026-10-24)",
                "architecture": "MobileNetV2 (archived copy)",
                "created_at": (manifest or {}).get("created_at") if isinstance(manifest, dict) else None,
                "dataset": {},
                "evaluation": {
                    "accuracy": None,
                    "accuracy_pct": None,
                    "note": "No held-out evaluation report is stored for this backup.",
                },
                "file_size_bytes": size,
                "file_size_mb": _mb(size),
                "format": "Keras .keras",
                "status": "Archived",
                "artifact": "ml/models/backups/pre_retrain_20261024_131011/owner_barong_model.keras",
                "comparable": False,
            }
        )

    return versions


def build_analytics(*, measure_latency: bool = False) -> dict[str, Any]:
    metrics = load_active_metrics()
    model_path = active_model_path()
    classes = list(metrics.get("classes") or CLASS_KEYS)
    cm = metrics.get("confusion_matrix")
    scored = metrics_from_confusion(cm, classes) if cm else {
        "per_class": [],
        "macro": {},
        "weighted": {},
        "accuracy": metrics.get("test_accuracy"),
        "accuracy_pct": _pct(metrics.get("test_accuracy")),
        "support_total": metrics.get("test_images") or 0,
    }

    report_path = active_dir() / "classification_report.txt"
    report_text = report_path.read_text(encoding="utf-8") if report_path.is_file() else ""
    parsed_report = parse_classification_report(report_text)

    # Prefer report text for display when it matches class set; else CM-derived.
    per_class = scored.get("per_class") or []
    if parsed_report and parsed_report.get("per_class"):
        merged = []
        for key in classes:
            row = next((r for r in per_class if r["key"] == key), None)
            rpt = parsed_report["per_class"].get(key) or {}
            precision = rpt.get("precision", row["precision"] if row else None)
            recall = rpt.get("recall", row["recall"] if row else None)
            f1 = rpt.get("f1", row["f1"] if row else None)
            support = rpt.get("support", row["support"] if row else 0)
            merged.append(
                {
                    "key": key,
                    "label": CLASS_LABELS.get(key, key.title()),
                    "precision": precision,
                    "recall": recall,
                    "f1": f1,
                    "support": support,
                    "precision_pct": _pct(precision),
                    "recall_pct": _pct(recall),
                    "f1_pct": _pct(f1),
                }
            )
        per_class = merged

    history = epoch_history(metrics)
    deploy = _safe_json(active_dir() / "deploy_log.json")
    version = str(metrics.get("version") or "")
    status = "Active" if model_path and metrics else ("Not Available" if not model_path else "Evaluating")
    if model_path and not metrics:
        status = "Active"

    overview = {
        "name": metrics.get("model") or "MobileNetV2 textile classifier",
        "version": version or None,
        "status": status,
        "last_evaluation_at": metrics.get("generated_at"),
        "deployed_at": metrics.get("deployed_at")
        or (deploy.get("deployed_at") if isinstance(deploy, dict) else None),
        "classes": [CLASS_LABELS.get(c, c) for c in classes],
        "class_count": len(classes),
        "dataset": {
            "train_images": metrics.get("train_images"),
            "val_images": metrics.get("val_images"),
            "test_images": metrics.get("test_images"),
            "seed": metrics.get("seed"),
            "identifier": f"held-out test ({metrics.get('test_images')} images)"
            if metrics.get("test_images")
            else None,
        },
        "metrics_source": metrics.get("_source_path"),
        "image_size": metrics.get("image_size"),
    }

    performance = {
        "available": bool(metrics.get("test_accuracy") is not None or cm),
        "averaging_note": "Macro and weighted averages shown; headline cards use macro precision/recall/F1 and held-out test accuracy.",
        "accuracy": metrics.get("test_accuracy", scored.get("accuracy")),
        "accuracy_pct": _pct(metrics.get("test_accuracy", scored.get("accuracy"))),
        "precision_pct": (scored.get("macro") or {}).get("precision_pct"),
        "recall_pct": (scored.get("macro") or {}).get("recall_pct"),
        "f1_pct": (scored.get("macro") or {}).get("f1_pct"),
        "macro": scored.get("macro") or {},
        "weighted": scored.get("weighted") or {},
        "per_class": per_class,
        "test_images": metrics.get("test_images") or scored.get("support_total"),
        "evaluation_split": "held-out test",
        "not_training_accuracy": True,
    }

    # Normalize confusion for UI
    confusion = {
        "available": bool(cm),
        "labels": [CLASS_LABELS.get(c, c) for c in classes],
        "keys": classes,
        "matrix": cm or [],
        "row_normalized": [],
        "explanation": "Rows are true labels; columns are predicted labels. Diagonal cells are correct predictions.",
    }
    if cm:
        norm = []
        for row in cm:
            total = sum(row) or 1
            norm.append([round(100.0 * v / total, 1) for v in row])
        confusion["row_normalized"] = norm

    training_runs = []
    if history.get("available") or metrics:
        training_runs.append(
            {
                "id": version or "main_run",
                "name": version or "Main classifier training",
                "architecture": metrics.get("model") or "MobileNetV2",
                "trained_at": metrics.get("generated_at"),
                "duration": None,
                "duration_note": "Wall-clock duration was not recorded in metrics.json.",
                "dataset": overview["dataset"],
                "epochs_completed": history.get("epochs_completed"),
                "best_validation_metric": {
                    "name": "val_accuracy",
                    "value": history.get("best_val_accuracy"),
                    "value_pct": _pct(history.get("best_val_accuracy")),
                },
                "final": {
                    "train_accuracy_pct": _pct(history.get("final_train_accuracy")),
                    "val_accuracy_pct": _pct(history.get("final_val_accuracy")),
                    "train_loss": history.get("final_train_loss"),
                    "val_loss": history.get("final_val_loss"),
                },
                "status": "Completed" if history.get("available") else "Completed",
                "history": history,
            }
        )

    versions = list_model_versions()
    size_bytes = model_path.stat().st_size if model_path and model_path.is_file() else None

    if measure_latency:
        latency = measure_inference_latency(persist=True)
    else:
        latency = load_inference_benchmark(model_path, version) or {
            "available": False,
            "message": "No cached latency benchmark yet. Use Refresh timing to measure local model.predict latency.",
            "cached": False,
        }

    limitations = []
    if not metrics:
        limitations.append("No metrics.json found under ml/models/active or Owner/models.")
    if not cm:
        limitations.append("Confusion matrix missing from evaluation artifacts.")
    if not history.get("available"):
        limitations.append("Per-epoch training history arrays were not found.")
    if len([v for v in versions if v.get("comparable")]) < 2:
        limitations.append(
            "Only one evaluated model version is available for numeric comparison; "
            "archived backups without evaluation reports cannot be ranked by accuracy."
        )

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overview": overview,
        "performance": performance,
        "confusion": confusion,
        "training_runs": training_runs,
        "history": history,
        "versions": versions,
        "efficiency": {
            "model_size_mb": _mb(size_bytes),
            "model_size_bytes": size_bytes,
            "model_format": "Keras SavedModel (.keras)",
            "active_version": version or None,
            "artifact": str(model_path.name) if model_path else None,
            "latency": latency,
        },
        "limitations": limitations,
        "export": {
            "classification_report": report_text.strip() or None,
            "metrics_version": version or None,
        },
    }


def analytics_json(*, measure_latency: bool = False) -> dict[str, Any]:
    return build_analytics(measure_latency=measure_latency)
