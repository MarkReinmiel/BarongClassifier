"""Train provisional binary Piña vs Piña Silk classifier (MobileNetV2).

Reads ml/reports/variant_source_manifest.csv
Writes ml/models/variant/active/ (does not touch main app models until activate script).
"""

from __future__ import annotations

import csv
import json
import os
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from PIL import Image
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_class_weight

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "ml" / "reports" / "variant_source_manifest.csv"
OUT = ROOT / "ml" / "models" / "variant" / "active"
REPORTS = ROOT / "ml" / "reports"

CLASSES = ["pina", "pina_silk"]
DISPLAY = {"pina": "Piña", "pina_silk": "Piña Silk"}
IMAGE_SIZE = 224
SEED = 42
HEAD_EPOCHS = 15
FINE_EPOCHS = 8
BATCH_SIZE = 16
HEAD_LR = 1e-3
FINE_LR = 1e-5


def configure() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    random.seed(SEED)
    np.random.seed(SEED)
    tf.keras.utils.set_random_seed(SEED)


def load_manifest() -> list[dict]:
    rows = []
    with MANIFEST.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("include_in_variant_train", "").lower() not in {"1", "true", "yes"}:
                continue
            if row.get("split") not in {"train", "val", "test"}:
                continue
            if not row.get("prepared_path") or not Path(row["prepared_path"]).is_file():
                continue
            rows.append(row)
    if not rows:
        raise FileNotFoundError(f"No rows in {MANIFEST}. Run prepare_variant_dataset.py first.")
    return rows


def load_images(rows: list[dict]):
    images = np.empty((len(rows), IMAGE_SIZE, IMAGE_SIZE, 3), dtype=np.uint8)
    labels = np.empty(len(rows), dtype=np.int32)
    splits = []
    for i, row in enumerate(rows):
        with Image.open(row["prepared_path"]) as image:
            resized = image.convert("RGB").resize(
                (IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS
            )
            images[i] = np.asarray(resized, dtype=np.uint8)
        labels[i] = CLASSES.index(row["variant_label"])
        splits.append(row["split"])
    return images, labels, splits


def subset(x, y, splits, name):
    idx = [i for i, s in enumerate(splits) if s == name]
    if not idx:
        return np.empty((0, IMAGE_SIZE, IMAGE_SIZE, 3), dtype=np.uint8), np.empty((0,), dtype=np.int32)
    return x[idx], y[idx]


def build_model():
    base = tf.keras.applications.MobileNetV2(
        input_shape=(IMAGE_SIZE, IMAGE_SIZE, 3),
        include_top=False,
        weights="imagenet",
        pooling="avg",
    )
    base.trainable = False
    inputs = tf.keras.Input(shape=(IMAGE_SIZE, IMAGE_SIZE, 3))
    z = tf.keras.layers.RandomFlip("horizontal_and_vertical")(inputs)
    z = tf.keras.layers.RandomRotation(0.5)(z)
    z = tf.keras.layers.RandomZoom(0.15)(z)
    z = tf.keras.layers.RandomContrast(0.1)(z)
    z = tf.keras.applications.mobilenet_v2.preprocess_input(z)
    z = base(z, training=False)
    z = tf.keras.layers.Dropout(0.35)(z)
    outputs = tf.keras.layers.Dense(len(CLASSES), activation="softmax", name="class_probs")(z)
    return tf.keras.Model(inputs, outputs, name="barong_pina_variant"), base


def compile_model(model, lr):
    model.compile(
        optimizer=tf.keras.optimizers.Adam(lr),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )


def fit_stage(model, x_tr, y_tr, x_va, y_va, epochs, class_weight):
    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss" if len(x_va) else "loss",
            patience=4,
            restore_best_weights=True,
        )
    ]
    validation_data = (x_va, y_va) if len(x_va) else None
    return model.fit(
        x_tr,
        y_tr,
        validation_data=validation_data,
        epochs=epochs,
        batch_size=min(BATCH_SIZE, max(1, len(x_tr))),
        class_weight=class_weight,
        callbacks=callbacks,
        verbose=1,
    )


def evaluate(model, x, y, tag: str) -> dict:
    if len(x) == 0:
        return {"tag": tag, "n": 0, "note": "empty split"}
    probs = model.predict(x, verbose=0)
    pred = np.argmax(probs, axis=1)
    label_ids = list(range(len(CLASSES)))
    report = classification_report(
        y,
        pred,
        labels=label_ids,
        target_names=CLASSES,
        output_dict=True,
        zero_division=0,
    )
    cm = confusion_matrix(y, pred, labels=label_ids).tolist()
    acc = float((pred == y).mean())
    return {
        "tag": tag,
        "n": int(len(y)),
        "accuracy": acc,
        "macro_f1": float(report["macro avg"]["f1-score"]),
        "per_class": {
            c: {
                "precision": float(report[c]["precision"]),
                "recall": float(report[c]["recall"]),
                "f1": float(report[c]["f1-score"]),
                "support": int(report[c]["support"]),
            }
            for c in CLASSES
        },
        "confusion_matrix": cm,
        "class_order": CLASSES,
    }


def pick_threshold(model, x_va, y_va) -> float:
    """Choose min confidence on predicted class using val set; default 0.55."""
    if len(x_va) == 0:
        return 0.55
    probs = model.predict(x_va, verbose=0)
    conf = probs.max(axis=1)
    # Keep threshold at median of correct predictions, floored
    pred = probs.argmax(axis=1)
    correct = conf[pred == y_va]
    if len(correct) == 0:
        return 0.55
    thr = float(np.clip(np.percentile(correct, 20), 0.50, 0.80))
    return thr


def main() -> int:
    configure()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_manifest()
    print(f"Rows: {len(rows)}  labels={Counter(r['variant_label'] for r in rows)}  splits={Counter(r['split'] for r in rows)}")
    x, y, splits = load_images(rows)
    x_tr, y_tr = subset(x, y, splits, "train")
    x_va, y_va = subset(x, y, splits, "val")
    x_te, y_te = subset(x, y, splits, "test")
    print(f"train={len(x_tr)} val={len(x_va)} test={len(x_te)}")

    weights = compute_class_weight("balanced", classes=np.arange(len(CLASSES)), y=y_tr)
    class_weight = {i: float(w) for i, w in enumerate(weights)}
    print("class_weight", class_weight)

    model, base = build_model()
    compile_model(model, HEAD_LR)
    hist1 = fit_stage(model, x_tr, y_tr, x_va, y_va, HEAD_EPOCHS, class_weight)

    base.trainable = True
    for layer in base.layers[:-40]:
        layer.trainable = False
    compile_model(model, FINE_LR)
    hist2 = fit_stage(model, x_tr, y_tr, x_va, y_va, FINE_EPOCHS, class_weight)

    version = datetime.now(timezone.utc).strftime("variant_%Y%m%d_%H%M%S")
    model_path = OUT / "barong_pina_variant.keras"
    model.save(model_path)

    metrics = {
        "version": version,
        "train": evaluate(model, x_tr, y_tr, "train"),
        "val": evaluate(model, x_va, y_va, "val"),
        "test": evaluate(model, x_te, y_te, "test"),
        "acceptance_threshold": pick_threshold(model, x_va if len(x_va) else x_tr, y_va if len(x_va) else y_tr),
        "class_weight": class_weight,
        "limitations": [
            "Provisional: only 2 Piña Silk physical samples.",
            "Test silk sample differs from train silk sample (good) but diversity is tiny.",
            "Retrain when ~150 images across many distinct silk textiles arrive.",
        ],
        "history": {
            "head_epochs": len(hist1.history.get("loss", [])),
            "fine_epochs": len(hist2.history.get("loss", [])),
        },
    }

    labels = {
        "classes": CLASSES,
        "display": DISPLAY,
        "image_size": IMAGE_SIZE,
        "version": version,
        "acceptance_threshold": metrics["acceptance_threshold"],
        "role": "pina_variant",
        "provisional": True,
    }
    (OUT / "labels.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (REPORTS / "VARIANT_MODEL_TRAINING_REPORT.md").write_text(
        "\n".join(
            [
                "# Piña Variant Model Training Report (Provisional)",
                "",
                f"**Version:** `{version}`",
                f"**Artifact:** `{model_path}`",
                "",
                "## Test metrics",
                "",
                f"- Accuracy: **{metrics['test'].get('accuracy', 'n/a')}**",
                f"- Macro F1: **{metrics['test'].get('macro_f1', 'n/a')}**",
                f"- N test: **{metrics['test'].get('n', 0)}**",
                f"- Confusion matrix (rows=true, cols=pred, order={CLASSES}): `{metrics['test'].get('confusion_matrix')}`",
                "",
                "## Per-class (test)",
                "",
                json.dumps(metrics["test"].get("per_class", {}), indent=2),
                "",
                f"**Acceptance threshold (val-derived):** {metrics['acceptance_threshold']}",
                "",
                "## Limitations",
                "",
                *[f"- {x}" for x in metrics["limitations"]],
                "",
                "150 more Piña Silk photos help **only if** they come from many different textiles",
                "(not 150 shots of the same cloth).",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # confusion plot
    if metrics["test"]["n"]:
        cm = np.array(metrics["test"]["confusion_matrix"])
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.imshow(cm, cmap="Blues")
        ax.set_xticks(range(len(CLASSES)))
        ax.set_yticks(range(len(CLASSES)))
        ax.set_xticklabels(CLASSES)
        ax.set_yticklabels(CLASSES)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("True")
        for i in range(len(CLASSES)):
            for j in range(len(CLASSES)):
                ax.text(j, i, str(cm[i, j]), ha="center", va="center")
        fig.tight_layout()
        fig.savefig(REPORTS / "variant_confusion_test.png", dpi=120)
        plt.close(fig)

    print(json.dumps({"version": version, "test": metrics["test"], "threshold": metrics["acceptance_threshold"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
