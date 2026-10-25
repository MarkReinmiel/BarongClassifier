"""Calibrate the offline relevance / OOD gate on held-out splits.

Uses the production main CNN without retraining it:
  - Fit class centroids on TRAIN embeddings (penultimate layer).
  - Tune distance / MSP / quality thresholds on VAL (+ synthetic OOD).
  - Report FAR/FRR and related metrics on TEST (+ held-out synthetic OOD).

Writes:
  ml/models/active/relevance_gate.json
  Customer/models/relevance_gate.json
  Owner/models/relevance_gate.json
  ml/reports/RELEVANCE_GATE_EVAL.md
  ml/reports/relevance_gate_metrics.json

Honest note: synthetic OOD (noise / solids / scrambled pixels) is a weak proxy for
real unrelated photos. Mark experimental until a curated OOD photo set exists.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Customer"))

from app.ml.relevance_gate import (  # noqa: E402
    STATUS_CLASSIFIED,
    STATUS_POOR,
    STATUS_UNCERTAIN,
    STATUS_UNDEFINED,
    assess_image_quality,
    cosine_distances,
    softmax_entropy,
)

ACTIVE = ROOT / "ml" / "models" / "active"
REPORTS = ROOT / "ml" / "reports"
MANIFEST = REPORTS / "source_manifest.csv"
CLASSES = ["cocoon", "jusi", "pina"]
IMAGE_SIZE = 224
SEED = 42


def configure() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    random.seed(SEED)
    np.random.seed(SEED)
    tf.keras.utils.set_random_seed(SEED)


def load_keras(path: Path):
    return tf.keras.models.load_model(path)


def feature_model(model):
    dense = model.layers[-1]
    return tf.keras.Model(inputs=model.inputs, outputs=[dense.input, dense.output])


def load_split_images(split: str) -> tuple[np.ndarray, np.ndarray]:
    import csv

    rows = []
    with MANIFEST.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("include_in_main_train", "").lower() not in {"1", "true", "yes"}:
                continue
            if row.get("split") != split:
                continue
            path = Path(row["prepared_path"])
            if path.is_file() and row.get("main_class") in CLASSES:
                rows.append(row)
    if not rows:
        raise FileNotFoundError(f"No {split} rows in {MANIFEST}")
    x = np.empty((len(rows), IMAGE_SIZE, IMAGE_SIZE, 3), dtype=np.uint8)
    y = np.empty((len(rows),), dtype=np.int32)
    for i, row in enumerate(rows):
        with Image.open(row["prepared_path"]) as im:
            x[i] = np.asarray(
                im.convert("RGB").resize((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS),
                dtype=np.uint8,
            )
        y[i] = CLASSES.index(row["main_class"])
    return x, y


def synthetic_ood(n: int = 60) -> np.ndarray:
    """Held-out synthetic non-textile proxies (not used for centroid fitting)."""
    out = np.empty((n, IMAGE_SIZE, IMAGE_SIZE, 3), dtype=np.uint8)
    rng = np.random.default_rng(SEED + 7)
    for i in range(n):
        kind = i % 5
        if kind == 0:
            out[i] = rng.integers(0, 256, size=(IMAGE_SIZE, IMAGE_SIZE, 3), dtype=np.uint8)
        elif kind == 1:
            out[i] = np.full((IMAGE_SIZE, IMAGE_SIZE, 3), int(rng.integers(0, 40)), dtype=np.uint8)
        elif kind == 2:
            out[i] = np.full((IMAGE_SIZE, IMAGE_SIZE, 3), int(rng.integers(220, 256)), dtype=np.uint8)
        elif kind == 3:
            base = rng.integers(0, 256, size=(16, 16, 3), dtype=np.uint8)
            out[i] = np.asarray(
                Image.fromarray(base).resize((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.NEAREST)
            )
        else:
            # Smooth gradient — no fabric texture.
            ys = np.linspace(0, 255, IMAGE_SIZE, dtype=np.float32)[:, None]
            xs = np.linspace(0, 255, IMAGE_SIZE, dtype=np.float32)[None, :]
            g = np.clip(ys + xs, 0, 255).astype(np.uint8)
            out[i] = np.stack([g, np.roll(g, 40, axis=0), np.roll(g, 80, axis=1)], axis=-1)
    return out


def embed(feat_m, images: np.ndarray, batch: int = 32):
    feats = []
    probs = []
    for i in range(0, len(images), batch):
        f, p = feat_m.predict(images[i : i + batch], verbose=0)
        feats.append(f)
        probs.append(p)
    return np.concatenate(feats), np.concatenate(probs)


def fit_centroids(feats: np.ndarray, y: np.ndarray) -> dict[str, list[float]]:
    centroids = {}
    for idx, name in enumerate(CLASSES):
        subset = feats[y == idx]
        if len(subset) == 0:
            raise RuntimeError(f"No train embeddings for {name}")
        centroids[name] = subset.mean(axis=0).astype(np.float32).tolist()
    return centroids


def score_batch(feats, probs, centroids_arr, cfg_quality):
    rows = []
    for i in range(len(feats)):
        dists = cosine_distances(feats[i], centroids_arr)
        min_d = float(dists.min())
        max_p = float(probs[i].max())
        ent = softmax_entropy(probs[i])
        rows.append({"min_dist": min_d, "max_prob": max_p, "entropy": ent})
    return rows


def decide(row, cfg) -> str:
    if row.get("quality_status") == STATUS_POOR:
        return STATUS_POOR
    if row["min_dist"] > cfg["max_centroid_distance"]:
        return STATUS_UNDEFINED
    if row["min_dist"] > cfg["uncertain_centroid_distance"]:
        return STATUS_UNCERTAIN
    if row["max_prob"] < cfg["min_softmax_confidence"] or row["entropy"] > cfg["max_entropy"]:
        return STATUS_UNCERTAIN
    return STATUS_CLASSIFIED


def main() -> None:
    configure()
    model_path = ACTIVE / "main_classifier.keras"
    if not model_path.is_file():
        # Fall back to app-deployed model
        model_path = ROOT / "Customer" / "models" / "barong_model.keras"
    if not model_path.is_file():
        raise FileNotFoundError("No main classifier keras file found.")

    print(f"Loading {model_path}", flush=True)
    model = load_keras(model_path)
    feat_m = feature_model(model)

    x_tr, y_tr = load_split_images("train")
    x_va, y_va = load_split_images("val")
    x_te, y_te = load_split_images("test")
    ood_val = synthetic_ood(40)
    ood_test = synthetic_ood(60)

    print("Embedding train/val/test + synthetic OOD…", flush=True)
    f_tr, p_tr = embed(feat_m, x_tr)
    f_va, p_va = embed(feat_m, x_va)
    f_te, p_te = embed(feat_m, x_te)
    f_ov, p_ov = embed(feat_m, ood_val)
    f_ot, p_ot = embed(feat_m, ood_test)

    centroids = fit_centroids(f_tr, y_tr)
    centroids_arr = np.stack([np.asarray(centroids[c], dtype=np.float32) for c in CLASSES])

    # Quality thresholds from train ID distribution (5th percentile laplacian).
    lap_vars = []
    bright = []
    for img in x_tr:
        status, m = assess_image_quality(img, {
            "min_brightness": 0.0,
            "max_brightness": 1.0,
            "min_laplacian_var": 0.0,
        })
        lap_vars.append(m["laplacian_var"])
        bright.append(m["brightness"])
    # Cap blur threshold so soft-but-usable phone captures are not all rejected.
    min_lap = float(np.clip(np.percentile(lap_vars, 5) * 0.35, 12.0, 80.0))
    min_b = float(max(0.05, np.percentile(bright, 1) * 0.5))
    max_b = float(min(0.98, np.percentile(bright, 99) + 0.05))

    id_va = score_batch(f_va, p_va, centroids_arr, None)
    ood_va_scores = score_batch(f_ov, p_ov, centroids_arr, None)

    # Tune max_centroid_distance on VAL to keep ID accept high while rejecting OOD.
    candidates = sorted({round(float(r["min_dist"]), 3) for r in id_va + ood_va_scores})
    best = None
    for thr in candidates:
        uncertain = max(0.05, thr * 0.75)
        cfg = {
            "max_centroid_distance": thr,
            "uncertain_centroid_distance": uncertain,
            "min_softmax_confidence": 0.45,
            "max_entropy": 1.0,
        }
        id_accept = sum(1 for r in id_va if decide(r, cfg) == STATUS_CLASSIFIED) / max(1, len(id_va))
        ood_reject = sum(
            1
            for r in ood_va_scores
            if decide(r, cfg) in {STATUS_UNDEFINED, STATUS_UNCERTAIN, STATUS_POOR}
        ) / max(1, len(ood_va_scores))
        # Prefer high OOD reject with ID accept >= 0.85
        score = ood_reject + (0.15 if id_accept >= 0.85 else -1.0) + 0.2 * id_accept
        if best is None or score > best[0]:
            best = (score, cfg, id_accept, ood_reject)

    assert best is not None
    _, cfg, val_id_accept, val_ood_reject = best
    cfg.update(
        {
            "min_brightness": min_b,
            "max_brightness": max_b,
            "min_laplacian_var": min_lap,
            "min_softmax_confidence": 0.45,
            "max_entropy": 1.05,
        }
    )

    # Held-out TEST evaluation (thresholds frozen).
    id_te = score_batch(f_te, p_te, centroids_arr, None)
    ood_te = score_batch(f_ot, p_ot, centroids_arr, None)

    # Attach quality for a few deliberately poor synthetic images.
    poor = np.zeros((8, IMAGE_SIZE, IMAGE_SIZE, 3), dtype=np.uint8)
    t0 = time.perf_counter()
    for _ in range(10):
        _ = feat_m.predict(x_te[:1], verbose=0)
    latency_ms = (time.perf_counter() - t0) / 10 * 1000

    def summarize(id_rows, ood_rows, label):
        id_dec = [decide(r, cfg) for r in id_rows]
        ood_dec = [decide(r, cfg) for r in ood_rows]
        far = sum(1 for d in ood_dec if d == STATUS_CLASSIFIED) / max(1, len(ood_dec))
        frr = sum(1 for d in id_dec if d != STATUS_CLASSIFIED) / max(1, len(id_dec))
        return {
            "split": label,
            "n_id": len(id_rows),
            "n_ood_synthetic": len(ood_rows),
            "false_acceptance_rate_synthetic_ood": far,
            "false_rejection_rate_id": frr,
            "id_accept_rate": 1.0 - frr,
            "ood_reject_rate_synthetic": 1.0 - far,
            "id_status_counts": {s: id_dec.count(s) for s in sorted(set(id_dec))},
            "ood_status_counts": {s: ood_dec.count(s) for s in sorted(set(ood_dec))},
        }

    val_metrics = summarize(id_va, ood_va_scores, "val")
    test_metrics = summarize(id_te, ood_te, "test")

    # Main-class confusion on TEST images that the gate accepts (textile CNN unchanged).
    pred = p_te.argmax(axis=1)
    accepted = [i for i, r in enumerate(id_te) if decide(r, cfg) == STATUS_CLASSIFIED]
    if accepted:
        from sklearn.metrics import classification_report, confusion_matrix

        y_true = y_te[accepted]
        y_pred = pred[accepted]
        report = classification_report(
            y_true, y_pred, labels=[0, 1, 2], target_names=CLASSES, output_dict=True, zero_division=0
        )
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1, 2]).tolist()
    else:
        report = {}
        cm = []

    poor_hits = 0
    for img in poor:
        st, _ = assess_image_quality(img, cfg)
        if st == STATUS_POOR:
            poor_hits += 1

    payload = {
        "version": datetime.now(timezone.utc).strftime("relevance_%Y%m%d_%H%M%S"),
        "experimental": True,
        "enabled": True,
        "method": "hybrid_centroid_msp_quality",
        "limitations": [
            "Synthetic OOD only (noise/solids/gradients); not a curated unrelated-photo set.",
            "False-acceptance rates on real-world OOD (faces, cars, other fabrics) are unknown.",
            "Centroid distance can reject unusual textile crops that differ from train framing.",
            "Softmax confidence is a secondary signal only; it is not trusted alone for OOD.",
        ],
        "classes": CLASSES,
        "image_size": IMAGE_SIZE,
        "model_source": str(model_path.relative_to(ROOT)).replace("\\", "/"),
        "centroids": centroids,
        **cfg,
        "val_tuning": {
            "id_accept_rate": val_id_accept,
            "synthetic_ood_reject_rate": val_ood_reject,
        },
        "eval": {
            "val": val_metrics,
            "test": test_metrics,
            "per_class_on_gate_accepted_test": report,
            "confusion_matrix_gate_accepted_test": cm,
            "poor_black_images_flagged": poor_hits,
            "poor_black_images_total": len(poor),
            "approx_feature_forward_latency_ms": latency_ms,
        },
    }

    targets = [
        ACTIVE / "relevance_gate.json",
        ROOT / "Customer" / "models" / "relevance_gate.json",
        ROOT / "Owner" / "models" / "relevance_gate.json",
        REPORTS / "relevance_gate_metrics.json",
    ]
    text = json.dumps(payload, indent=2)
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        # metrics file should not need huge centroids duplicated? Keep full for apps.
        if path.name == "relevance_gate_metrics.json":
            path.write_text(text, encoding="utf-8")
        else:
            path.write_text(text, encoding="utf-8")
        print(f"Wrote {path}", flush=True)

    md = [
        "# Relevance / OOD Gate Evaluation (Experimental)",
        "",
        f"**Version:** `{payload['version']}`",
        f"**Method:** `{payload['method']}`",
        f"**Model (unchanged):** `{payload['model_source']}`",
        "",
        "## Selected method",
        "",
        "1. Image quality (brightness + Laplacian variance).",
        "2. Cosine distance from MobileNetV2 penultimate features to class centroids (train).",
        "3. Softmax max-probability / entropy as secondary soft checks.",
        "",
        "No paid vision API. Production textile CNN weights were not retrained.",
        "",
        "## Limitations (read before trusting metrics)",
        "",
        *[f"- {x}" for x in payload["limitations"]],
        "",
        "## Thresholds (tuned on VAL; frozen for TEST)",
        "",
        f"- `max_centroid_distance`: **{cfg['max_centroid_distance']}**",
        f"- `uncertain_centroid_distance`: **{cfg['uncertain_centroid_distance']}**",
        f"- `min_softmax_confidence`: **{cfg['min_softmax_confidence']}**",
        f"- `min_laplacian_var`: **{cfg['min_laplacian_var']}**",
        "",
        "## Held-out TEST (synthetic OOD)",
        "",
        f"- ID false-rejection rate: **{test_metrics['false_rejection_rate_id']:.3f}**",
        f"- Synthetic OOD false-acceptance rate: **{test_metrics['false_acceptance_rate_synthetic_ood']:.3f}**",
        f"- Approx feature forward latency: **{latency_ms:.1f} ms**",
        "",
        "These OOD figures are **not** real-world unrelated photo rates.",
        "",
        "## Confusion matrix (TEST textiles accepted by gate)",
        "",
        f"`{cm}`",
        "",
        "Per-class report JSON is in `relevance_gate_metrics.json`.",
        "",
    ]
    report_path = REPORTS / "RELEVANCE_GATE_EVAL.md"
    report_path.write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote {report_path}", flush=True)
    print(json.dumps({"test": test_metrics, "latency_ms": latency_ms}, indent=2), flush=True)


if __name__ == "__main__":
    main()
