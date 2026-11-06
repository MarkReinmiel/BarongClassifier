"""Background worker: train a candidate CNN into a versioned registry directory.

Never writes to Frontend Customer/Owner production model paths.
Updates training_jobs + model_versions via DATABASE_URL when available.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(REPO_ROOT / "ml" / "scripts"))

# Reuse the existing main trainer helpers.
import train_main_classifier as trainer  # noqa: E402


def _db_execute(sql: str, params: dict | None = None) -> None:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        print("DATABASE_URL not set; skipping DB status updates", flush=True)
        return
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, pool_pre_ping=True)
        with engine.begin() as conn:
            conn.execute(text(sql), params or {})
    except Exception as error:
        print(f"DB update failed: {error}", flush=True)


def update_job(*, status: str | None = None, pct: float | None = None, message: str | None = None, error: str | None = None) -> None:
    job_id = os.environ.get("TRAINING_JOB_ID")
    if not job_id:
        return
    sets = ["updated_at = timezone('utc', now())"]
    params: dict = {"id": job_id}
    if status:
        sets.append("status = :status")
        params["status"] = status
        if status in {"succeeded", "failed", "cancelled"}:
            sets.append("finished_at = timezone('utc', now())")
    if pct is not None:
        sets.append("progress_pct = :pct")
        params["pct"] = float(pct)
    if message is not None:
        sets.append("progress_message = :message")
        params["message"] = message[:500]
    if error is not None:
        sets.append("error_message = :error")
        params["error"] = error[:2000]
    _db_execute(
        f"update public.training_jobs set {', '.join(sets)} where id = cast(:id as uuid)",
        params,
    )


def update_version(*, status: str, metrics: dict | None = None) -> None:
    version_id = os.environ.get("MODEL_VERSION_ID")
    if not version_id:
        return
    params = {"id": version_id, "status": status}
    sets = ["status = :status", "updated_at = timezone('utc', now())"]
    if metrics is not None:
        sets.append("metrics_json = cast(:metrics as jsonb)")
        params["metrics"] = json.dumps(metrics)
    _db_execute(
        f"update public.model_versions set {', '.join(sets)} where id = cast(:id as uuid)",
        params,
    )


def main() -> int:
    artifact_dir = Path(os.environ.get("ARTIFACT_DIR") or "")
    if not artifact_dir:
        print("ARTIFACT_DIR required", flush=True)
        return 2
    artifact_dir.mkdir(parents=True, exist_ok=True)

    try:
        update_job(status="running", pct=5, message="Preparing revision dataset")
        trainer.configure()
        trainer.ACTIVE = artifact_dir
        trainer.REPORTS = artifact_dir

        # Stage immutable revision snapshot (master + approved contributions).
        plan_path = artifact_dir / "dataset_plan.json"
        if plan_path.is_file():
            import stage_revision_dataset as stager

            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            update_job(pct=8, message="Merging approved images into master + snapshot")
            stage_summary = stager.stage_from_plan(plan, log=lambda m: print(m, flush=True))
            (artifact_dir / "dataset_snapshot.json").write_text(
                json.dumps(
                    {k: v for k, v in stage_summary.items() if k != "staged"},
                    indent=2,
                ),
                encoding="utf-8",
            )
            # Train only from the immutable snapshot — never mutate production keras.
            trainer.MAIN_DATA = Path(stage_summary["snapshot_dir"])
            print(
                f"Revision snapshot ready: {stage_summary['snapshot_dir']} "
                f"counts={stage_summary['class_counts']} "
                f"added={stage_summary['added_to_master']} "
                f"dupes={stage_summary['duplicates_skipped']}",
                flush=True,
            )
        else:
            print("No dataset_plan.json; training from default master folders.", flush=True)

        counts = trainer.folder_class_counts()
        use_folder = all(counts.get(c, 0) >= 1 for c in trainer.CLASSES) and (
            sum(counts.values()) >= 30
        )
        update_job(pct=15, message="Loading images")
        if use_folder:
            print(f"Using folder/snapshot dataset: {counts}", flush=True)
            x, y, splits = trainer.load_from_folders()
        else:
            rows = trainer.load_manifest()
            x, y, splits = trainer.load_images(rows)

        x_tr, y_tr = trainer.subset(x, y, splits, "train")
        x_va, y_va = trainer.subset(x, y, splits, "val")
        x_te, y_te = trainer.subset(x, y, splits, "test")
        if len(x_te) == 0 or len(x_va) == 0:
            raise RuntimeError("Empty val/test split — cannot evaluate fairly.")

        from sklearn.utils.class_weight import compute_class_weight
        import numpy as np
        import tensorflow as tf
        from sklearn.metrics import classification_report, confusion_matrix

        weights = compute_class_weight(
            class_weight="balanced", classes=np.arange(len(trainer.CLASSES)), y=y_tr
        )
        class_weight = {i: float(w) for i, w in enumerate(weights)}

        update_job(pct=25, message="Stage 1: frozen backbone")
        model, base = trainer.build_model()
        trainer.compile_model(model, trainer.HEAD_LR)
        h1 = trainer.fit_stage(
            model, x_tr, y_tr, x_va, y_va, trainer.HEAD_EPOCHS, class_weight
        )

        update_job(pct=60, message="Stage 2: fine-tune")
        base.trainable = True
        for layer in base.layers[: -trainer.FINE_TUNE_AT]:
            layer.trainable = False
        for layer in base.layers[-trainer.FINE_TUNE_AT :]:
            if isinstance(layer, tf.keras.layers.BatchNormalization):
                layer.trainable = False
        trainer.compile_model(model, trainer.FINE_LR)
        h2 = trainer.fit_stage(
            model, x_tr, y_tr, x_va, y_va, trainer.FINE_EPOCHS, class_weight
        )

        history = {
            k: list(h1.history[k]) + list(h2.history.get(k, [])) for k in h1.history
        }

        update_job(pct=85, message="Evaluating on held-out test set")
        probs = model.predict(x_te, batch_size=trainer.BATCH_SIZE, verbose=0)
        pred = probs.argmax(axis=1)
        acc = float((pred == y_te).mean())
        matrix = confusion_matrix(y_te, pred, labels=[0, 1, 2])
        report = classification_report(
            y_te,
            pred,
            labels=[0, 1, 2],
            target_names=[trainer.DISPLAY[c] for c in trainer.CLASSES],
            digits=3,
            zero_division=0,
        )

        version = datetime.now(timezone.utc).strftime("main_%Y%m%d_%H%M%S")
        model_path = artifact_dir / "main_classifier.keras"
        model.save(model_path)
        labels = {
            "classes": trainer.CLASSES,
            "image_size": trainer.IMAGE_SIZE,
            "version": version,
        }
        (artifact_dir / "labels.json").write_text(
            json.dumps(labels, indent=2), encoding="utf-8"
        )

        # Preserve production relevance gate if present (do not overwrite app files).
        gate_src = (
            REPO_ROOT
            / "Frontend"
            / "src"
            / "owner"
            / "models"
            / "relevance_gate.json"
        )
        if gate_src.is_file():
            import shutil

            shutil.copy2(gate_src, artifact_dir / "relevance_gate.json")

        metrics = {
            "version": version,
            "model": "MobileNetV2",
            "image_size": trainer.IMAGE_SIZE,
            "seed": trainer.SEED,
            "test_accuracy": acc,
            "test_images": int(len(y_te)),
            "train_images": int(len(y_tr)),
            "val_images": int(len(y_va)),
            "classes": trainer.CLASSES,
            "confusion_matrix": matrix.tolist(),
            "history": history,
            "deployed_to_apps": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "artifact_dir": str(artifact_dir),
            "dataset_root": str(getattr(trainer, "MAIN_DATA", "")),
            "candidate_only": True,
            "production_untouched": True,
        }
        (artifact_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2), encoding="utf-8"
        )
        (artifact_dir / "classification_report.txt").write_text(report, encoding="utf-8")

        print(report, flush=True)
        print(f"Test accuracy: {acc:.3f}", flush=True)
        print(f"Saved candidate only: {model_path}", flush=True)
        print("Production Customer/Owner weights were NOT modified.", flush=True)

        # Auto-evaluate against deployment threshold so Owner controls unlock correctly.
        min_acc = float(os.environ.get("MODEL_MIN_TEST_ACCURACY") or 0.85)
        passed = acc >= min_acc
        eval_status = "evaluation_passed" if passed else "evaluation_failed"
        metrics["evaluation"] = {
            "auto": True,
            "passed": passed,
            "min_required_accuracy": min_acc,
            "test_accuracy": acc,
        }
        (artifact_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2), encoding="utf-8"
        )
        update_version(status=eval_status, metrics=metrics)
        update_job(
            status="succeeded",
            pct=100,
            message=(
                f"Training complete. Auto-eval {'PASSED' if passed else 'FAILED'} "
                f"(test_accuracy={acc:.3f}, min={min_acc:.3f})."
            ),
        )
        print(
            f"Auto-evaluation: {'PASSED' if passed else 'FAILED'} "
            f"(acc={acc:.3f}, min={min_acc:.3f})",
            flush=True,
        )
        return 0
    except Exception as error:
        traceback.print_exc()
        update_job(status="failed", message="Training failed", error=str(error))
        update_version(status="failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
