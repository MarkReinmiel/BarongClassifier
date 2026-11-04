"""Train main 3-class model from ml/data/main_classifier using Stage B splits.

Writes candidates to ml/models/active/ — does NOT overwrite Customer/Owner models.
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
MANIFEST = ROOT / "ml" / "reports" / "source_manifest.csv"
MAIN_DATA = ROOT / "ml" / "data" / "main_classifier"
ACTIVE = ROOT / "ml" / "models" / "active"
REPORTS = ROOT / "ml" / "reports"

CLASSES = ["cocoon", "jusi", "pina"]
DISPLAY = {"cocoon": "Cocoon", "jusi": "Jusi", "pina": "Piña"}
IMAGE_SIZE = 224
SEED = 42
HEAD_EPOCHS = 12
FINE_EPOCHS = 8
BATCH_SIZE = 32
HEAD_LR = 1e-3
FINE_LR = 1e-5
FINE_TUNE_AT = 30
IMG_EXT = {".jpg", ".jpeg", ".jpe", ".png", ".webp", ".bmp"}
# Prefer balanced folder dataset (300/class) when present; else Stage B manifest.
USE_FOLDER_IF_BALANCED = True
FOLDER_VAL_FRAC = 0.15
FOLDER_TEST_FRAC = 0.15


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
            if row.get("include_in_main_train", "").lower() in {"1", "true", "yes"}:
                if row.get("prepared_path") and row.get("split") in {"train", "val", "test"}:
                    rows.append(row)
    if not rows:
        raise FileNotFoundError(f"No trainable rows in {MANIFEST}. Run prepare_main_dataset.py first.")
    return rows


def folder_class_counts() -> dict[str, int]:
    counts = {}
    for class_name in CLASSES:
        folder = MAIN_DATA / class_name
        if not folder.is_dir():
            counts[class_name] = 0
            continue
        counts[class_name] = sum(
            1 for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXT
        )
    return counts


def load_from_folders() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load all images under main_classifier/{class} and assign stratified splits."""
    from sklearn.model_selection import train_test_split

    paths: list[Path] = []
    labels_list: list[int] = []
    for class_name in CLASSES:
        folder = MAIN_DATA / class_name
        files = sorted(
            p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXT
        )
        for path in files:
            paths.append(path)
            labels_list.append(CLASSES.index(class_name))

    if not paths:
        raise FileNotFoundError(f"No images under {MAIN_DATA}")

    idx = np.arange(len(paths))
    y = np.asarray(labels_list, dtype=np.int32)
    idx_tv, idx_te = train_test_split(
        idx, test_size=FOLDER_TEST_FRAC, random_state=SEED, stratify=y
    )
    y_tv = y[idx_tv]
    val_ratio = FOLDER_VAL_FRAC / (1.0 - FOLDER_TEST_FRAC)
    idx_tr, idx_va = train_test_split(
        idx_tv, test_size=val_ratio, random_state=SEED, stratify=y_tv
    )

    split_of = {}
    for i in idx_tr:
        split_of[int(i)] = "train"
    for i in idx_va:
        split_of[int(i)] = "val"
    for i in idx_te:
        split_of[int(i)] = "test"

    images = np.empty((len(paths), IMAGE_SIZE, IMAGE_SIZE, 3), dtype=np.uint8)
    labels = np.empty(len(paths), dtype=np.int32)
    splits: list[str] = []
    for i, path in enumerate(paths):
        with Image.open(path) as image:
            resized = image.convert("RGB").resize(
                (IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS
            )
            images[i] = np.asarray(resized, dtype=np.uint8)
        labels[i] = labels_list[i]
        splits.append(split_of[i])
        if (i + 1) % 50 == 0 or i + 1 == len(paths):
            print(f"Loaded {i + 1}/{len(paths)}", flush=True)
    return images, labels, splits


def load_images(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    images = np.empty((len(rows), IMAGE_SIZE, IMAGE_SIZE, 3), dtype=np.uint8)
    labels = np.empty(len(rows), dtype=np.int32)
    splits = []
    for i, row in enumerate(rows):
        path = Path(row["prepared_path"])
        with Image.open(path) as image:
            resized = image.convert("RGB").resize(
                (IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS
            )
            images[i] = np.asarray(resized, dtype=np.uint8)
        labels[i] = CLASSES.index(row["main_class"])
        splits.append(row["split"])
        if (i + 1) % 50 == 0 or i + 1 == len(rows):
            print(f"Loaded {i + 1}/{len(rows)}", flush=True)
    return images, labels, splits


def subset(x, y, splits, name):
    idx = [i for i, s in enumerate(splits) if s == name]
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
    z = tf.keras.layers.RandomZoom(0.1)(z)
    z = tf.keras.applications.mobilenet_v2.preprocess_input(z)
    z = base(z, training=False)
    z = tf.keras.layers.Dropout(0.3)(z)
    outputs = tf.keras.layers.Dense(len(CLASSES), activation="softmax", name="class_probs")(z)
    return tf.keras.Model(inputs, outputs, name="barong_main_v2"), base


def compile_model(model, lr):
    model.compile(
        optimizer=tf.keras.optimizers.Adam(lr),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )


def fit_stage(model, x_tr, y_tr, x_va, y_va, epochs, class_weight):
    cb = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=3, restore_best_weights=True
        )
    ]
    return model.fit(
        x_tr,
        y_tr,
        validation_data=(x_va, y_va),
        epochs=epochs,
        batch_size=BATCH_SIZE,
        class_weight=class_weight,
        callbacks=cb,
        verbose=2,
    )


def main() -> int:
    configure()
    ACTIVE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    counts = folder_class_counts()
    use_folder = USE_FOLDER_IF_BALANCED and all(counts.get(c, 0) >= 300 for c in CLASSES)
    if use_folder:
        print(f"Using balanced folder dataset under {MAIN_DATA}: {counts}")
        x, y, splits = load_from_folders()
        print(f"Trainable images: {len(y)}")
        print(Counter((splits[i], CLASSES[int(y[i])]) for i in range(len(y))))
    else:
        rows = load_manifest()
        print(f"Trainable rows (manifest): {len(rows)}")
        print(Counter((r["split"], r["main_class"]) for r in rows))
        x, y, splits = load_images(rows)

    x_tr, y_tr = subset(x, y, splits, "train")
    x_va, y_va = subset(x, y, splits, "val")
    x_te, y_te = subset(x, y, splits, "test")
    if len(x_te) == 0 or len(x_va) == 0:
        raise RuntimeError("Empty val/test split — cannot evaluate fairly.")

    weights = compute_class_weight(
        class_weight="balanced", classes=np.arange(len(CLASSES)), y=y_tr
    )
    class_weight = {i: float(w) for i, w in enumerate(weights)}

    model, base = build_model()
    compile_model(model, HEAD_LR)
    print("Stage 1: frozen backbone")
    h1 = fit_stage(model, x_tr, y_tr, x_va, y_va, HEAD_EPOCHS, class_weight)

    print("Stage 2: fine-tune")
    base.trainable = True
    for layer in base.layers[:-FINE_TUNE_AT]:
        layer.trainable = False
    for layer in base.layers[-FINE_TUNE_AT:]:
        if isinstance(layer, tf.keras.layers.BatchNormalization):
            layer.trainable = False
    compile_model(model, FINE_LR)
    h2 = fit_stage(model, x_tr, y_tr, x_va, y_va, FINE_EPOCHS, class_weight)

    history = {
        k: list(h1.history[k]) + list(h2.history.get(k, [])) for k in h1.history
    }

    probs = model.predict(x_te, batch_size=BATCH_SIZE, verbose=0)
    pred = probs.argmax(axis=1)
    acc = float((pred == y_te).mean())
    matrix = confusion_matrix(y_te, pred, labels=[0, 1, 2])
    report = classification_report(
        y_te,
        pred,
        labels=[0, 1, 2],
        target_names=[DISPLAY[c] for c in CLASSES],
        digits=3,
        zero_division=0,
    )

    version = datetime.now(timezone.utc).strftime("main_%Y%m%d_%H%M%S")
    model_path = ACTIVE / "main_classifier.keras"
    model.save(model_path)
    labels = {"classes": CLASSES, "image_size": IMAGE_SIZE, "version": version}
    (ACTIVE / "labels.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")

    metrics = {
        "version": version,
        "model": "MobileNetV2",
        "image_size": IMAGE_SIZE,
        "seed": SEED,
        "test_accuracy": acc,
        "test_images": int(len(y_te)),
        "train_images": int(len(y_tr)),
        "val_images": int(len(y_va)),
        "classes": CLASSES,
        "confusion_matrix": matrix.tolist(),
        "history": history,
        "deployed_to_apps": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (ACTIVE / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (ACTIVE / "classification_report.txt").write_text(report, encoding="utf-8")
    (REPORTS / "MODEL_TRAINING_REPORT.md").write_text(
        "\n".join(
            [
                "# Main classifier training report",
                "",
                f"- Version: `{version}`",
                f"- Artifact: `{model_path}`",
                f"- Test accuracy: **{acc:.3f}** on {len(y_te)} images",
                f"- Train / val / test images: {len(y_tr)} / {len(y_va)} / {len(y_te)}",
                f"- Data source: {'balanced folders (300/class)' if use_folder else 'source_manifest.csv'}",
                "- Piña Silk variant: **retired** — silk images folded into Piña.",
                "- Deployed to Customer/Owner: **no** (pending activation gate).",
                "",
                "## Classification report",
                "```",
                report,
                "```",
                "",
                "## Confusion matrix (rows=true, cols=pred; cocoon,jusi,pina)",
                "```",
                str(matrix.tolist()),
                "```",
                "",
                "## Limitations",
                "- physical_sample_id mostly unknown; splits use filename/IMG groups.",
                "- pia_2 / pia_2.1 included under user provisional acceptance.",
                "- Former pia_silk / pina_silk images trained as Piña.",
            ]
        ),
        encoding="utf-8",
    )

    # quick plot
    epochs = np.arange(1, len(history["loss"]) + 1)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].plot(epochs, history["loss"], label="train")
    axes[0].plot(epochs, history["val_loss"], label="val")
    axes[1].plot(epochs, history["accuracy"], label="train")
    axes[1].plot(epochs, history["val_accuracy"], label="val")
    for ax, title in zip(axes, ("Loss", "Accuracy")):
        ax.set_title(title)
        ax.legend()
    fig.tight_layout()
    fig.savefig(ACTIVE / "training_history.png", dpi=140)
    plt.close(fig)

    print(report)
    print(f"Test accuracy: {acc:.3f}")
    print(f"Saved: {model_path}")
    print("NOT deployed to Customer/Owner — run activate script only after review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
