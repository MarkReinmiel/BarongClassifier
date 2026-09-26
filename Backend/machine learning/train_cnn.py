"""Train a CNN to classify Cocoon, Jusi, and Piña close-up photos.

Reads images from dataset/<class>/. Resizing and augmentation happen in memory
during training. Original dataset files, ZIP files, and the web app are not modified.

Run from the project root:

    python "Backend/machine learning/train_cnn.py"
"""

from __future__ import annotations

import csv
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from PIL import Image
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight

ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT / "dataset"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"

CLASSES = ["cocoon", "jusi", "pina"]
DISPLAY = {"cocoon": "Cocoon", "jusi": "Jusi", "pina": "Piña"}
IMAGE_SIZE = 224
SEED = 42
GROUP_PATTERN = re.compile(r"^(IMG_\d{8}_\d{6})(?:_\d+)?$", re.IGNORECASE)

HEAD_EPOCHS = 12
FINE_EPOCHS = 8
BATCH_SIZE = 32
HEAD_LEARNING_RATE = 1e-3
FINE_LEARNING_RATE = 1e-5
FINE_TUNE_AT = 30


def configure() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    random.seed(SEED)
    np.random.seed(SEED)
    tf.keras.utils.set_random_seed(SEED)


def capture_group(path: Path) -> str:
    match = GROUP_PATTERN.match(path.stem)
    if match:
        return match.group(1)
    return path.stem


def collect_records() -> list[dict]:
    records = []
    for label, class_name in enumerate(CLASSES):
        class_dir = DATASET_DIR / class_name
        if not class_dir.is_dir():
            raise FileNotFoundError(f"Missing class folder: {class_dir}")
        paths = sorted(
            p
            for p in class_dir.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"} and p.is_file()
        )
        if not paths:
            raise FileNotFoundError(f"No images in {class_dir}")
        for path in paths:
            records.append(
                {
                    "path": path,
                    "class_name": class_name,
                    "label": label,
                    "group": f"{class_name}/{capture_group(path)}",
                }
            )
    return records


def assign_splits(records: list[dict]) -> None:
    """Keep photos from the same capture second in one split."""
    groups_by_class: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()
    for record in records:
        if record["group"] in seen:
            continue
        seen.add(record["group"])
        groups_by_class[record["class_name"]].append(record["group"])

    split_of_group: dict[str, str] = {}
    for class_name, groups in groups_by_class.items():
        groups = sorted(groups)
        train_val, test = train_test_split(
            groups, test_size=0.15, random_state=SEED
        )
        train, val = train_test_split(
            train_val, test_size=0.15 / 0.85, random_state=SEED
        )
        for group in train:
            split_of_group[group] = "train"
        for group in val:
            split_of_group[group] = "val"
        for group in test:
            split_of_group[group] = "test"

    for record in records:
        record["split"] = split_of_group[record["group"]]


def load_images(records: list[dict]) -> np.ndarray:
    images = np.empty((len(records), IMAGE_SIZE, IMAGE_SIZE, 3), dtype=np.uint8)
    for index, record in enumerate(records):
        with Image.open(record["path"]) as image:
            resized = image.convert("RGB").resize(
                (IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS
            )
            images[index] = np.asarray(resized, dtype=np.uint8)
        if (index + 1) % 50 == 0 or index + 1 == len(records):
            print(f"Loaded {index + 1}/{len(records)} images", flush=True)
    return images


def subset(images: np.ndarray, records: list[dict], split: str):
    indexes = [i for i, record in enumerate(records) if record["split"] == split]
    x = images[indexes]
    y = np.array([records[i]["label"] for i in indexes], dtype=np.int32)
    return x, y


def build_model() -> tuple[tf.keras.Model, tf.keras.Model]:
    base = tf.keras.applications.MobileNetV2(
        input_shape=(IMAGE_SIZE, IMAGE_SIZE, 3),
        include_top=False,
        weights="imagenet",
        pooling="avg",
    )
    base.trainable = False

    inputs = tf.keras.Input(shape=(IMAGE_SIZE, IMAGE_SIZE, 3))
    x = tf.keras.layers.RandomFlip("horizontal_and_vertical")(inputs)
    x = tf.keras.layers.RandomRotation(0.5)(x)
    x = tf.keras.layers.RandomZoom(0.1)(x)
    x = tf.keras.applications.mobilenet_v2.preprocess_input(x)
    x = base(x, training=False)
    x = tf.keras.layers.Dropout(0.3)(x)
    outputs = tf.keras.layers.Dense(len(CLASSES), activation="softmax", name="class_probs")(x)
    model = tf.keras.Model(inputs, outputs, name="barong_mobilenetv2")
    return model, base


def compile_model(model: tf.keras.Model, learning_rate: float) -> None:
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )


def fit_stage(model, x_train, y_train, x_val, y_val, epochs: int, class_weight):
    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=3,
            restore_best_weights=True,
        )
    ]
    return model.fit(
        x_train,
        y_train,
        validation_data=(x_val, y_val),
        epochs=epochs,
        batch_size=BATCH_SIZE,
        class_weight=class_weight,
        callbacks=callbacks,
        verbose=2,
    )


def save_split(records: list[dict]) -> None:
    path = ARTIFACT_DIR / "split.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["filepath", "class", "group", "split"]
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "filepath": record["path"].relative_to(ROOT).as_posix(),
                    "class": record["class_name"],
                    "group": record["group"],
                    "split": record["split"],
                }
            )


def save_plots(history: dict, matrix: np.ndarray, stage_boundary: int) -> None:
    epochs = np.arange(1, len(history["loss"]) + 1)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].plot(epochs, history["loss"], label="Training loss")
    axes[0].plot(epochs, history["val_loss"], label="Validation loss")
    axes[1].plot(epochs, history["accuracy"], label="Training accuracy")
    axes[1].plot(epochs, history["val_accuracy"], label="Validation accuracy")
    for axis, ylabel in zip(axes, ("Loss", "Accuracy")):
        if 0 < stage_boundary < len(epochs):
            axis.axvline(stage_boundary + 0.5, color="gray", linestyle="--", linewidth=1)
        axis.set_xlabel("Epoch")
        axis.set_ylabel(ylabel)
        axis.legend()
    axes[0].set_title("Training and validation loss")
    axes[1].set_title("Training and validation accuracy")
    fig.tight_layout()
    fig.savefig(ARTIFACT_DIR / "training_history.png", dpi=140)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(5.5, 4.5))
    image = axis.imshow(matrix, cmap="Blues")
    fig.colorbar(image, ax=axis, label="Images")
    names = [DISPLAY[name] for name in CLASSES]
    axis.set_xticks(range(len(CLASSES)), names)
    axis.set_yticks(range(len(CLASSES)), names)
    axis.set_xlabel("Predicted class")
    axis.set_ylabel("Actual class")
    axis.set_title("Test-set confusion matrix")
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            axis.text(col, row, str(matrix[row, col]), ha="center", va="center")
    fig.tight_layout()
    fig.savefig(ARTIFACT_DIR / "confusion_matrix.png", dpi=140)
    plt.close(fig)


def orientation_check(model, x_test, y_test) -> float:
    """Rotate test photos 90 degrees and score again."""
    rotated = np.rot90(x_test, k=1, axes=(1, 2)).copy()
    probabilities = model.predict(rotated, batch_size=BATCH_SIZE, verbose=0)
    predicted = probabilities.argmax(axis=1)
    return float((predicted == y_test).mean())


def main() -> int:
    configure()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    print("BarongClassifier CNN training")
    print("Device: CPU")
    print(f"Dataset: {DATASET_DIR}")
    print()

    records = collect_records()
    assign_splits(records)
    counts = Counter((record["split"], record["class_name"]) for record in records)
    for split in ("train", "val", "test"):
        parts = [f"{DISPLAY[name]} {counts[(split, name)]}" for name in CLASSES]
        total = sum(counts[(split, name)] for name in CLASSES)
        print(f"{split}: {total} images ({', '.join(parts)})")
    print()

    images = load_images(records)
    x_train, y_train = subset(images, records, "train")
    x_val, y_val = subset(images, records, "val")
    x_test, y_test = subset(images, records, "test")

    weights = compute_class_weight(
        class_weight="balanced", classes=np.arange(len(CLASSES)), y=y_train
    )
    class_weight = {index: float(weight) for index, weight in enumerate(weights)}

    print("Building MobileNetV2. ImageNet weights download on the first run.")
    model, base = build_model()
    compile_model(model, HEAD_LEARNING_RATE)
    print("Stage 1: train the new classifier. The pretrained CNN stays frozen.")
    stage_one = fit_stage(
        model, x_train, y_train, x_val, y_val, HEAD_EPOCHS, class_weight
    )

    print("Stage 2: fine-tune the last CNN blocks at a small learning rate.")
    base.trainable = True
    for layer in base.layers[:-FINE_TUNE_AT]:
        layer.trainable = False
    for layer in base.layers[-FINE_TUNE_AT:]:
        if isinstance(layer, tf.keras.layers.BatchNormalization):
            layer.trainable = False
    compile_model(model, FINE_LEARNING_RATE)
    stage_two = fit_stage(
        model, x_train, y_train, x_val, y_val, FINE_EPOCHS, class_weight
    )

    history = {}
    for key in stage_one.history:
        history[key] = list(stage_one.history[key]) + list(stage_two.history.get(key, []))

    probabilities = model.predict(x_test, batch_size=BATCH_SIZE, verbose=0)
    predicted = probabilities.argmax(axis=1)
    test_accuracy = float((predicted == y_test).mean())
    rotated_accuracy = orientation_check(model, x_test, y_test)
    matrix = confusion_matrix(y_test, predicted, labels=[0, 1, 2])
    report = classification_report(
        y_test,
        predicted,
        labels=[0, 1, 2],
        target_names=[DISPLAY[name] for name in CLASSES],
        digits=3,
        zero_division=0,
    )

    model_path = ARTIFACT_DIR / "barong_mobilenetv2.keras"
    model.save(model_path)
    save_split(records)
    save_plots(history, matrix, stage_boundary=len(stage_one.history["loss"]))

    metrics = {
        "model": "MobileNetV2",
        "image_size": IMAGE_SIZE,
        "seed": SEED,
        "test_accuracy": test_accuracy,
        "rotated_test_accuracy": rotated_accuracy,
        "test_images": int(len(y_test)),
        "classes": CLASSES,
        "confusion_matrix": matrix.tolist(),
        "history": history,
    }
    (ARTIFACT_DIR / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    (ARTIFACT_DIR / "labels.json").write_text(
        json.dumps({"classes": CLASSES, "image_size": IMAGE_SIZE}, indent=2),
        encoding="utf-8",
    )
    (ARTIFACT_DIR / "classification_report.txt").write_text(report, encoding="utf-8")

    print()
    print(report)
    print(f"Test accuracy: {test_accuracy:.3f} on {len(y_test)} images")
    print(f"Accuracy after rotating those test images 90 degrees: {rotated_accuracy:.3f}")
    print(f"Saved model: {model_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
