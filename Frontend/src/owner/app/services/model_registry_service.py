"""Owner model registry: versioned candidates, background training, deploy/rollback.

Production inference keeps using Frontend app model files until an Owner deploys.
Candidate training writes only under ml/models/registry/<version_label>/.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import OwnerUser

REPO_ROOT = Path(__file__).resolve().parents[5]  # .../Frontend/src/owner/app/services → repo
REGISTRY_ROOT = REPO_ROOT / "ml" / "models" / "registry"
ACTIVE_CANDIDATE = REPO_ROOT / "ml" / "models" / "active"
POINTER_PATH = REGISTRY_ROOT / "active_pointer.json"

# Minimum held-out accuracy to allow deployment (configurable via env).
DEFAULT_MIN_TEST_ACCURACY = 0.85

_JOB_LOCK = threading.Lock()


class ModelRegistryError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _min_accuracy() -> float:
    raw = (
        current_app.config.get("MODEL_MIN_TEST_ACCURACY")
        or os.environ.get("MODEL_MIN_TEST_ACCURACY")
        or DEFAULT_MIN_TEST_ACCURACY
    )
    try:
        return float(raw)
    except (TypeError, ValueError):
        return DEFAULT_MIN_TEST_ACCURACY


def _app_model_targets() -> list[tuple[Path, Path]]:
    return [
        (
            REPO_ROOT / "Frontend" / "src" / "customer" / "models" / "barong_model.keras",
            REPO_ROOT / "Frontend" / "src" / "customer" / "models" / "labels.json",
        ),
        (
            REPO_ROOT / "Frontend" / "src" / "owner" / "models" / "barong_model.keras",
            REPO_ROOT / "Frontend" / "src" / "owner" / "models" / "labels.json",
        ),
    ]


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _write_pointer(version_label: str, model_path: Path, labels_path: Path) -> None:
    POINTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    POINTER_PATH.write_text(
        json.dumps(
            {
                "version_label": version_label,
                "model_path": str(model_path),
                "labels_path": str(labels_path),
                "updated_at": _utc_now().isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def contribution_dataset_stats() -> dict[str, Any]:
    """Count approved / pool images available for future labeled training."""
    empty = {
        "approved": 0,
        "added_to_dataset": 0,
        "labeled_for_training": 0,
        "trainable_contribution_count": 0,
        "unlabeled_pool": 0,
        "rejected": 0,
        "cumulative_pool": 0,
    }
    try:
        rows = db.session.execute(
            text(
                """
                select
                  review_status,
                  count(*)::int as n,
                  count(*) filter (where verified_label is not null and verified_label <> '')::int
                    as labeled
                from public.classification_reviews
                group by review_status
                """
            )
        ).mappings().all()
        stats = dict(empty)
        for row in rows:
            status = row["review_status"]
            n = int(row["n"] or 0)
            labeled = int(row["labeled"] or 0)
            if status == "approved":
                stats["approved"] = n
                stats["labeled_for_training"] += labeled
                stats["unlabeled_pool"] += max(0, n - labeled)
            elif status == "added_to_dataset":
                stats["added_to_dataset"] = n
                stats["labeled_for_training"] += labeled
                stats["unlabeled_pool"] += max(0, n - labeled)
            elif status == "rejected":
                stats["rejected"] = n
        stats["cumulative_pool"] = int(stats["approved"]) + int(stats["added_to_dataset"])
        # Trainable = approved/pool with verified class or usable predicted class.
        stats["trainable_contribution_count"] = len(list_trainable_contribution_images())
        return stats
    except SQLAlchemyError:
        db.session.rollback()
        return empty


def _display_revision(major: int, revision: int) -> str:
    return f"v{int(major)}.{int(revision)}"


def _resolve_next_revision(
    *,
    new_major: bool,
    production: dict[str, Any] | None,
) -> tuple[int, int, str]:
    """Return (major, revision, display_label) for the next training candidate."""
    if new_major:
        max_major = int(
            db.session.execute(
                text("select coalesce(max(major_version), 0)::int from public.model_versions")
            ).scalar()
            or 0
        )
        major = max(max_major, int((production or {}).get("major_version") or 0)) + 1
        revision = 1
    else:
        major = int((production or {}).get("major_version") or 1)
        max_rev = int(
            db.session.execute(
                text(
                    """
                    select coalesce(max(revision_number), 0)::int
                    from public.model_versions
                    where major_version = :major
                    """
                ),
                {"major": major},
            ).scalar()
            or 0
        )
        # Always advance past both DB max and the live production revision.
        prod_rev = int((production or {}).get("revision_number") or 0)
        revision = max(max_rev, prod_rev) + 1
        if revision <= 1 and not production:
            major = 1
            revision = 1
    return major, revision, _display_revision(major, revision)


TRAINABLE_CLASSES = ("cocoon", "jusi", "pina")
MASTER_DATASET = REPO_ROOT / "ml" / "data" / "main_classifier"
SNAPSHOT_ROOT = REPO_ROOT / "ml" / "data" / "snapshots"


def _normalize_train_label(raw: str | None) -> str | None:
    if not raw:
        return None
    key = (
        str(raw)
        .strip()
        .lower()
        .replace("ñ", "n")
        .replace("piña", "pina")
        .replace("pina silk", "pina")
    )
    if key in {"undefined", "undefined textile", "ood", "other"}:
        return None
    if key in TRAINABLE_CLASSES:
        return key
    for name in TRAINABLE_CLASSES:
        if name in key:
            return name
    return None


def list_trainable_contribution_images() -> list[dict[str, Any]]:
    """Approved / dataset-pool images with a usable textile class for CNN training.

    Rejected, pending, uncertain, and undefined-textile predictions are excluded.
    Prefers Owner verified_label; otherwise uses predicted_label only when the Owner
    already approved the photo (suitability gate).
    """
    try:
        rows = db.session.execute(
            text(
                """
                select
                  r.classification_id::text as classification_id,
                  r.image_url,
                  r.verified_label,
                  r.predicted_label,
                  r.review_status,
                  to_char(r.reviewed_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
                    as reviewed_at
                from public.classification_reviews r
                where r.review_status in ('approved', 'added_to_dataset')
                  and r.image_url is not null
                  and length(trim(r.image_url)) > 0
                order by r.reviewed_at nulls last, r.created_at
                """
            )
        ).mappings().all()
    except SQLAlchemyError:
        db.session.rollback()
        return []

    items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for row in rows:
        url = (row.get("image_url") or "").strip()
        if not url or url in seen_urls:
            continue
        label = _normalize_train_label(row.get("verified_label")) or _normalize_train_label(
            row.get("predicted_label")
        )
        if not label:
            continue
        seen_urls.add(url)
        items.append(
            {
                "classification_id": row["classification_id"],
                "image_url": url,
                "label": label,
                "label_source": (
                    "verified_label"
                    if _normalize_train_label(row.get("verified_label"))
                    else "predicted_label_on_approve"
                ),
                "review_status": row["review_status"],
                "reviewed_at": row.get("reviewed_at"),
            }
        )
    return items


def _build_dataset_snapshot(
    *,
    major: int,
    revision: int,
    production: dict[str, Any] | None,
) -> dict[str, Any]:
    stats = contribution_dataset_stats()
    contributions = list_trainable_contribution_images()
    prev_summary = (production or {}).get("dataset_summary") or {}
    if isinstance(prev_summary, str):
        prev_summary = json.loads(prev_summary or "{}")
    prev_contrib = int(prev_summary.get("trainable_contribution_count") or 0)
    newly_added = max(0, len(contributions) - prev_contrib)
    snapshot_id = f"ds_{major}_{revision}_{_utc_now().strftime('%Y%m%d_%H%M%S')}"
    by_class: dict[str, int] = {c: 0 for c in TRAINABLE_CLASSES}
    for item in contributions:
        by_class[item["label"]] = by_class.get(item["label"], 0) + 1
    return {
        **stats,
        "snapshot_id": snapshot_id,
        "major_version": major,
        "revision_number": revision,
        "base_dataset": "ml/data/main_classifier",
        "snapshot_dir": str(SNAPSHOT_ROOT / snapshot_id),
        "includes_original_training_data": True,
        "includes_previously_approved": True,
        "includes_newly_approved": True,
        "excludes_rejected_and_unverified": True,
        "trainable_contribution_count": len(contributions),
        "contribution_by_class": by_class,
        "newly_added_since_production": newly_added,
        "previous_production_label": (
            (production or {}).get("display_revision")
            or (production or {}).get("version_label")
        ),
        "contributions": contributions,
        "note": (
            "Immutable revision snapshot = original folder dataset + all Owner-approved "
            "customer images with a textile class. Rejected / pending / undefined excluded. "
            "Duplicates skipped by content hash."
        ),
    }


def group_versions_by_major(versions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for item in versions:
        major = int(item.get("major_version") or item.get("version_number") or 1)
        bucket = grouped.setdefault(
            major,
            {"major_version": major, "label": f"Model v{major}", "revisions": []},
        )
        revision = int(item.get("revision_number") or 1)
        bucket["revisions"].append(
            {
                **item,
                "display_revision": _display_revision(major, revision),
            }
        )
    for bucket in grouped.values():
        bucket["revisions"].sort(
            key=lambda row: int(row.get("revision_number") or 0),
            reverse=True,
        )
    return [grouped[k] for k in sorted(grouped.keys(), reverse=True)]


def ensure_production_seed() -> dict[str, Any] | None:
    """Register the current app model as v1/active if the registry is empty."""
    try:
        existing = db.session.execute(
            text("select count(*)::int from public.model_versions")
        ).scalar() or 0
        if existing:
            return get_production_model()

        owner_model = (
            REPO_ROOT / "Frontend" / "src" / "owner" / "models" / "barong_model.keras"
        )
        owner_labels = (
            REPO_ROOT / "Frontend" / "src" / "owner" / "models" / "labels.json"
        )
        metrics: dict[str, Any] = {}
        metrics_path = ACTIVE_CANDIDATE / "metrics.json"
        if metrics_path.is_file():
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        version_label = "v1.1"
        artifact_dir = REGISTRY_ROOT / f"v1.1_{_utc_now().strftime('%Y%m%d_%H%M%S')}"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        if owner_model.is_file():
            shutil.copy2(owner_model, artifact_dir / "main_classifier.keras")
        if owner_labels.is_file():
            shutil.copy2(owner_labels, artifact_dir / "labels.json")
        if metrics_path.is_file():
            shutil.copy2(metrics_path, artifact_dir / "metrics.json")

        row = db.session.execute(
            text(
                """
                insert into public.model_versions (
                  version_label, version_number, major_version, revision_number,
                  status, artifact_dir, metrics_json, dataset_summary, is_production,
                  notes, dataset_snapshot_id, deployed_at, created_at, updated_at
                ) values (
                  :version_label, 1, 1, 1,
                  'active', :artifact_dir,
                  cast(:metrics_json as jsonb), cast(:dataset_summary as jsonb),
                  true, :notes, :snapshot_id, timezone('utc', now()),
                  timezone('utc', now()), timezone('utc', now())
                )
                returning id::text as id, version_label, version_number,
                          major_version, revision_number, status,
                          is_production, artifact_dir, metrics_json, dataset_summary,
                          to_char(deployed_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC')
                            as deployed_at
                """
            ),
            {
                "version_label": version_label,
                "artifact_dir": str(artifact_dir),
                "metrics_json": json.dumps(metrics),
                "dataset_summary": json.dumps(
                    {
                        "source": "seeded_from_production",
                        "classes": ["cocoon", "jusi", "pina"],
                        "major_version": 1,
                        "revision_number": 1,
                        "cumulative_pool": 0,
                    }
                ),
                "notes": "Seeded from currently deployed Owner/Customer production weights (v1.1).",
                "snapshot_id": "ds_1_1_seed",
            },
        ).mappings().first()
        db.session.commit()
        if owner_model.is_file() and owner_labels.is_file():
            _write_pointer(version_label, owner_model, owner_labels)
        return dict(row) if row else None
    except SQLAlchemyError as error:
        db.session.rollback()
        current_app.logger.exception("ensure_production_seed failed")
        raise ModelRegistryError("Could not seed model registry.", 503) from error


def get_production_model() -> dict[str, Any] | None:
    try:
        row = db.session.execute(
            text(
                """
                select
                  id::text as id,
                  version_label,
                  version_number,
                  coalesce(major_version, version_number, 1)::int as major_version,
                  coalesce(revision_number, 1)::int as revision_number,
                  status,
                  artifact_dir,
                  is_production,
                  metrics_json,
                  dataset_summary,
                  dataset_snapshot_id,
                  notes,
                  to_char(created_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC') as created_at,
                  to_char(deployed_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC') as deployed_at
                from public.model_versions
                where is_production = true
                order by major_version desc, revision_number desc
                limit 1
                """
            )
        ).mappings().first()
        if not row:
            return None
        item = dict(row)
        item["display_revision"] = _display_revision(
            item["major_version"], item["revision_number"]
        )
        return item
    except SQLAlchemyError:
        db.session.rollback()
        return None


def list_model_versions(limit: int = 50) -> list[dict[str, Any]]:
    try:
        rows = db.session.execute(
            text(
                """
                select
                  id::text as id,
                  version_label,
                  version_number,
                  coalesce(major_version, version_number, 1)::int as major_version,
                  coalesce(revision_number, 1)::int as revision_number,
                  status,
                  artifact_dir,
                  is_production,
                  metrics_json,
                  dataset_summary,
                  dataset_snapshot_id,
                  notes,
                  to_char(created_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC') as created_at,
                  to_char(deployed_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC') as deployed_at
                from public.model_versions
                order by major_version desc, revision_number desc
                limit :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
        items = []
        for row in rows:
            item = dict(row)
            item["display_revision"] = _display_revision(
                item["major_version"], item["revision_number"]
            )
            summary = item.get("dataset_summary") or {}
            if isinstance(summary, str):
                try:
                    summary = json.loads(summary or "{}")
                except json.JSONDecodeError:
                    summary = {}
            metrics = item.get("metrics_json") or {}
            if isinstance(metrics, str):
                try:
                    metrics = json.loads(metrics or "{}")
                except json.JSONDecodeError:
                    metrics = {}
            item["added_image_count"] = int(
                summary.get("newly_added_since_production")
                or summary.get("trainable_contribution_count")
                or 0
            )
            item["test_accuracy"] = metrics.get("test_accuracy")
            item["artifact_location"] = item.get("artifact_dir")
            items.append(item)
        return items
    except SQLAlchemyError:
        db.session.rollback()
        return []


def get_latest_candidate() -> dict[str, Any] | None:
    try:
        row = db.session.execute(
            text(
                """
                select
                  v.id::text as id,
                  v.version_label,
                  v.version_number,
                  coalesce(v.major_version, v.version_number, 1)::int as major_version,
                  coalesce(v.revision_number, 1)::int as revision_number,
                  v.status,
                  v.artifact_dir,
                  v.is_production,
                  v.metrics_json,
                  v.dataset_summary,
                  v.dataset_snapshot_id,
                  v.notes,
                  to_char(v.created_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC') as created_at,
                  j.id::text as job_id,
                  j.status as job_status,
                  j.progress_pct,
                  j.progress_message,
                  j.error_message,
                  j.attempt,
                  to_char(j.started_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC') as job_started_at,
                  to_char(j.finished_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC') as job_finished_at
                from public.model_versions v
                left join lateral (
                  select *
                  from public.training_jobs tj
                  where tj.model_version_id = v.id
                  order by tj.created_at desc
                  limit 1
                ) j on true
                where v.is_production = false
                order by v.major_version desc nulls last, v.revision_number desc nulls last
                limit 1
                """
            )
        ).mappings().first()
        if not row:
            return None
        item = dict(row)
        item["display_revision"] = _display_revision(
            item["major_version"], item["revision_number"]
        )
        return item
    except SQLAlchemyError:
        db.session.rollback()
        return None


def get_active_training_job() -> dict[str, Any] | None:
    try:
        row = db.session.execute(
            text(
                """
                select
                  j.id::text as id,
                  j.model_version_id::text as model_version_id,
                  j.status,
                  j.progress_pct,
                  j.progress_message,
                  j.error_message,
                  j.attempt,
                  j.pid,
                  j.log_path,
                  v.version_label
                from public.training_jobs j
                join public.model_versions v on v.id = j.model_version_id
                where j.status in ('queued', 'running')
                order by j.created_at desc
                limit 1
                """
            )
        ).mappings().first()
        return dict(row) if row else None
    except SQLAlchemyError:
        db.session.rollback()
        return None


def list_deployments(limit: int = 20) -> list[dict[str, Any]]:
    try:
        rows = db.session.execute(
            text(
                """
                select
                  d.id::text as id,
                  d.action,
                  d.success,
                  d.details,
                  d.actor_user_id,
                  to_char(d.created_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC') as created_at,
                  v.version_label,
                  p.version_label as previous_version_label
                from public.model_deployments d
                join public.model_versions v on v.id = d.model_version_id
                left join public.model_versions p on p.id = d.previous_version_id
                order by d.created_at desc
                limit :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
        return [dict(r) for r in rows]
    except SQLAlchemyError:
        db.session.rollback()
        return []


def dashboard_payload() -> dict[str, Any]:
    ensure_production_seed()
    production = get_production_model()
    candidate = get_latest_candidate()
    active_job = get_active_training_job()
    versions = list_model_versions()
    deployments = list_deployments()
    dataset = contribution_dataset_stats()
    prod_metrics = production.get("metrics_json") if production else {}
    if isinstance(prod_metrics, str):
        prod_metrics = json.loads(prod_metrics or "{}")
    cand_metrics = candidate.get("metrics_json") if candidate else {}
    if isinstance(cand_metrics, str):
        cand_metrics = json.loads(cand_metrics or "{}")

    classifications_handled = 0
    try:
        classifications_handled = int(
            db.session.execute(
                text("select count(*)::int from public.classifications")
            ).scalar()
            or 0
        )
    except SQLAlchemyError:
        db.session.rollback()

    major_groups = group_versions_by_major(versions)
    return {
        "production": production,
        "candidate": candidate,
        "active_job": active_job,
        "versions": versions,
        "version_groups": major_groups,
        "deployments": deployments,
        "dataset": dataset,
        "production_metrics": prod_metrics or {},
        "candidate_metrics": cand_metrics or {},
        "classifications_handled": classifications_handled,
        "min_test_accuracy": _min_accuracy(),
        "can_start_training": active_job is None,
        "can_retry": bool(
            candidate
            and candidate.get("status") in {"failed", "evaluation_failed"}
            and active_job is None
        ),
        "can_evaluate": bool(
            candidate
            and candidate.get("status")
            in {"pending_evaluation", "evaluation_passed", "evaluation_failed", "approved_for_deployment"}
        ),
        "can_deploy": bool(
            candidate
            and candidate.get("status") in {"evaluation_passed", "approved_for_deployment"}
        ),
        "can_rollback": bool(production and len(versions) > 1),
        "next_revision_preview": (
            _display_revision(
                int((production or {}).get("major_version") or 1),
                int(
                    db.session.execute(
                        text(
                            """
                            select coalesce(max(revision_number), 0)::int + 1
                            from public.model_versions
                            where major_version = :major
                            """
                        ),
                        {"major": int((production or {}).get("major_version") or 1)},
                    ).scalar()
                    or 1
                ),
            )
            if production
            else "v1.2"
        ),
    }


def start_training(
    actor: OwnerUser,
    *,
    retry: bool = False,
    new_major: bool = False,
) -> dict[str, Any]:
    """Queue a candidate training job as a revision under the current major (default).

    Pass new_major=True only when the Owner explicitly starts a new major generation.
    Never overwrites production weights.
    """
    if not _JOB_LOCK.acquire(blocking=False):
        raise ModelRegistryError("Another training action is already starting.", 409)
    try:
        ensure_production_seed()
        if get_active_training_job():
            raise ModelRegistryError(
                "A training job is already queued or running. Wait for it to finish.",
                409,
            )

        production = get_production_model()
        major, revision, display = _resolve_next_revision(
            new_major=new_major, production=production
        )
        next_number = int(
            db.session.execute(
                text("select coalesce(max(version_number), 0)::int + 1 from public.model_versions")
            ).scalar()
            or 1
        )
        stamp = _utc_now().strftime("%Y%m%d_%H%M%S")
        version_label = f"{display}_{stamp}"
        artifact_dir = REGISTRY_ROOT / version_label
        artifact_dir.mkdir(parents=True, exist_ok=True)
        # Immutable candidate path — never writes into production keras files.
        (artifact_dir / "CANDIDATE_ONLY.txt").write_text(
            "Independent candidate artifact. Production inference uses app model files until deploy.\n",
            encoding="utf-8",
        )
        dataset = _build_dataset_snapshot(
            major=major, revision=revision, production=production
        )
        # Immutable plan for the worker — staging happens off the request thread.
        plan_path = artifact_dir / "dataset_plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "snapshot_id": dataset["snapshot_id"],
                    "snapshot_dir": dataset["snapshot_dir"],
                    "master_dataset": str(MASTER_DATASET),
                    "major_version": major,
                    "revision_number": revision,
                    "display_revision": display,
                    "contributions": dataset.get("contributions") or [],
                    "newly_added_since_production": dataset.get(
                        "newly_added_since_production"
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        # Keep DB summary lean (omit full contribution URL list).
        dataset_for_db = {
            k: v for k, v in dataset.items() if k != "contributions"
        }

        version = db.session.execute(
            text(
                """
                insert into public.model_versions (
                  version_label, version_number, major_version, revision_number,
                  status, artifact_dir, parent_version_id, is_production, created_by,
                  metrics_json, dataset_summary, dataset_snapshot_id, notes,
                  created_at, updated_at
                ) values (
                  :version_label, :version_number, :major_version, :revision_number,
                  'training', :artifact_dir, cast(:parent_id as uuid), false, :created_by,
                  '{}'::jsonb, cast(:dataset_summary as jsonb), :snapshot_id, :notes,
                  timezone('utc', now()), timezone('utc', now())
                )
                returning id::text as id, version_label, version_number,
                          major_version, revision_number, status, artifact_dir
                """
            ),
            {
                "version_label": version_label,
                "version_number": next_number,
                "major_version": major,
                "revision_number": revision,
                "artifact_dir": str(artifact_dir),
                "parent_id": production.get("id") if production else None,
                "created_by": str(actor.id),
                "dataset_summary": json.dumps(dataset_for_db),
                "snapshot_id": dataset["snapshot_id"],
                "notes": (
                    "retry_revision"
                    if retry
                    else ("new_major" if new_major else "revision_under_current_major")
                ),
            },
        ).mappings().first()
        assert version is not None

        log_path = artifact_dir / "training.log"
        job = db.session.execute(
            text(
                """
                insert into public.training_jobs (
                  model_version_id, status, attempt, progress_pct, progress_message,
                  log_path, started_by, started_at, created_at, updated_at
                ) values (
                  cast(:model_version_id as uuid), 'queued', 1, 0, 'Queued',
                  :log_path, :started_by, timezone('utc', now()),
                  timezone('utc', now()), timezone('utc', now())
                )
                returning id::text as id
                """
            ),
            {
                "model_version_id": version["id"],
                "log_path": str(log_path),
                "started_by": str(actor.id),
            },
        ).mappings().first()
        db.session.commit()

        worker = REPO_ROOT / "ml" / "scripts" / "train_candidate_worker.py"
        env = os.environ.copy()
        env["MODEL_VERSION_ID"] = version["id"]
        env["TRAINING_JOB_ID"] = job["id"]
        env["ARTIFACT_DIR"] = str(artifact_dir)
        env["REPO_ROOT"] = str(REPO_ROOT)
        owner_env = REPO_ROOT / "Frontend" / "src" / "owner" / ".env"
        if owner_env.is_file() and not env.get("DATABASE_URL"):
            for line in owner_env.read_text(encoding="utf-8").splitlines():
                if line.startswith("DATABASE_URL="):
                    env["DATABASE_URL"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

        log_handle = log_path.open("a", encoding="utf-8")
        process = subprocess.Popen(
            [sys.executable, str(worker)],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        db.session.execute(
            text(
                """
                update public.training_jobs
                set status = 'running', pid = :pid, progress_message = 'Training process started',
                    updated_at = timezone('utc', now())
                where id = cast(:id as uuid)
                """
            ),
            {"id": job["id"], "pid": process.pid},
        )
        db.session.commit()
        log_handle.close()

        return {
            "ok": True,
            "version": dict(version),
            "display_revision": display,
            "major_version": major,
            "revision_number": revision,
            "new_major": new_major,
            "job_id": job["id"],
            "pid": process.pid,
            "dataset_snapshot": dataset_for_db,
            "message": (
                f"Started training revision {display} in the background. "
                f"Production remains on "
                f"{(production or {}).get('display_revision') or (production or {}).get('version_label') or 'current'}. "
                "Weights were not overwritten."
            ),
        }
    except ModelRegistryError:
        db.session.rollback()
        raise
    except SQLAlchemyError as error:
        db.session.rollback()
        current_app.logger.exception("start_training failed")
        raise ModelRegistryError("Could not start training.", 503) from error
    finally:
        _JOB_LOCK.release()


def evaluate_candidate(actor: OwnerUser, version_id: str | None = None) -> dict[str, Any]:
    candidate = None
    if version_id:
        candidate = db.session.execute(
            text(
                """
                select id::text as id, version_label, status, artifact_dir, metrics_json
                from public.model_versions
                where id::text = :id
                limit 1
                """
            ),
            {"id": version_id},
        ).mappings().first()
    else:
        candidate = get_latest_candidate()
    if not candidate:
        raise ModelRegistryError("No candidate model to evaluate.")

    artifact_dir = Path(candidate["artifact_dir"] or "")
    metrics_path = artifact_dir / "metrics.json"
    if not metrics_path.is_file():
        raise ModelRegistryError(
            "Candidate metrics are missing. Wait for training to finish or retry training."
        )
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    accuracy = float(metrics.get("test_accuracy") or 0)
    min_acc = _min_accuracy()
    passed = accuracy >= min_acc
    production = get_production_model()
    prod_metrics = production.get("metrics_json") if production else {}
    if isinstance(prod_metrics, str):
        prod_metrics = json.loads(prod_metrics or "{}")

    comparison = {
        "candidate_accuracy": accuracy,
        "production_accuracy": float((prod_metrics or {}).get("test_accuracy") or 0),
        "min_required_accuracy": min_acc,
        "improved_vs_production": accuracy
        >= float((prod_metrics or {}).get("test_accuracy") or 0),
    }
    status = "evaluation_passed" if passed else "evaluation_failed"
    db.session.execute(
        text(
            """
            update public.model_versions
            set status = :status,
                metrics_json = cast(:metrics as jsonb),
                updated_at = timezone('utc', now())
            where id = cast(:id as uuid)
            """
        ),
        {
            "id": candidate["id"],
            "status": status,
            "metrics": json.dumps(metrics),
        },
    )
    db.session.execute(
        text(
            """
            insert into public.model_evaluations (
              model_version_id, passed, metrics_json, compared_to_version_id, notes
            ) values (
              cast(:model_version_id as uuid), :passed, cast(:metrics as jsonb),
              cast(:compared_to as uuid), :notes
            )
            """
        ),
        {
            "model_version_id": candidate["id"],
            "passed": passed,
            "metrics": json.dumps({**metrics, "comparison": comparison}),
            "compared_to": production.get("id") if production else None,
            "notes": f"evaluated_by={actor.id}",
        },
    )
    db.session.commit()
    return {
        "ok": True,
        "passed": passed,
        "status": status,
        "metrics": metrics,
        "comparison": comparison,
        "message": (
            f"Evaluation passed (test accuracy {accuracy:.3f})."
            if passed
            else f"Evaluation failed (test accuracy {accuracy:.3f} < {min_acc:.3f}). Deployment blocked."
        ),
    }


def _invalidate_runtime_models() -> None:
    try:
        from app.ml import model_loader

        if hasattr(model_loader, "invalidate_cache"):
            model_loader.invalidate_cache()
    except Exception:
        current_app.logger.exception("Could not invalidate Owner model cache")


def deploy_candidate(actor: OwnerUser, version_id: str) -> dict[str, Any]:
    row = db.session.execute(
        text(
            """
            select id::text as id, version_label, status, artifact_dir, metrics_json
            from public.model_versions
            where id::text = :id
            limit 1
            """
        ),
        {"id": version_id},
    ).mappings().first()
    if not row:
        raise ModelRegistryError("Candidate version was not found.", 404)
    if row["status"] not in {"evaluation_passed", "approved_for_deployment"}:
        raise ModelRegistryError(
            "Only evaluation-passed candidates can be deployed.",
            400,
        )

    artifact_dir = Path(row["artifact_dir"])
    src_model = artifact_dir / "main_classifier.keras"
    src_labels = artifact_dir / "labels.json"
    if not src_model.is_file() or not src_labels.is_file():
        raise ModelRegistryError("Candidate model artifacts are missing.", 400)

    # Health check: load candidate separately without touching production cache first.
    try:
        from app.ml.model_loader import _load_keras_model

        probe = _load_keras_model(src_model)
        del probe
    except Exception as error:
        raise ModelRegistryError(f"Candidate health check failed: {error}", 400) from error

    previous = get_production_model()
    copied: list[dict[str, str]] = []
    try:
        for model_dest, labels_dest in _app_model_targets():
            model_dest.parent.mkdir(parents=True, exist_ok=True)
            # Atomic-ish swap: write sidecar then replace.
            tmp_model = model_dest.with_suffix(".keras.next")
            tmp_labels = labels_dest.with_suffix(".json.next")
            shutil.copy2(src_model, tmp_model)
            shutil.copy2(src_labels, tmp_labels)
            os.replace(tmp_model, model_dest)
            os.replace(tmp_labels, labels_dest)
            # Keep relevance gate sidecar if present on candidate.
            gate_src = artifact_dir / "relevance_gate.json"
            if gate_src.is_file():
                shutil.copy2(gate_src, model_dest.with_name("relevance_gate.json"))
            copied.append(
                {
                    "model": str(model_dest),
                    "labels": str(labels_dest),
                    "sha256": _sha256(model_dest),
                }
            )

        if previous:
            db.session.execute(
                text(
                    """
                    update public.model_versions
                    set is_production = false,
                        status = case when status = 'active' then 'archived' else status end,
                        updated_at = timezone('utc', now())
                    where id = cast(:id as uuid)
                    """
                ),
                {"id": previous["id"]},
            )
        db.session.execute(
            text(
                """
                update public.model_versions
                set is_production = true,
                    status = 'active',
                    deployed_at = timezone('utc', now()),
                    updated_at = timezone('utc', now())
                where id = cast(:id as uuid)
                """
            ),
            {"id": row["id"]},
        )
        db.session.execute(
            text(
                """
                insert into public.model_deployments (
                  model_version_id, previous_version_id, action, success,
                  actor_user_id, details
                ) values (
                  cast(:model_version_id as uuid), cast(:previous_version_id as uuid),
                  'deploy', true, :actor, cast(:details as jsonb)
                )
                """
            ),
            {
                "model_version_id": row["id"],
                "previous_version_id": previous.get("id") if previous else None,
                "actor": str(actor.id),
                "details": json.dumps({"targets": copied}),
            },
        )
        db.session.commit()
        owner_model = _app_model_targets()[1][0]
        owner_labels = _app_model_targets()[1][1]
        _write_pointer(row["version_label"], owner_model, owner_labels)
        _invalidate_runtime_models()
        return {
            "ok": True,
            "message": f"Deployed {row['version_label']} to Customer and Owner. Previous production kept for rollback.",
            "version_label": row["version_label"],
            "targets": copied,
        }
    except ModelRegistryError:
        db.session.rollback()
        raise
    except Exception as error:
        db.session.rollback()
        current_app.logger.exception("deploy_candidate failed")
        db.session.execute(
            text(
                """
                insert into public.model_deployments (
                  model_version_id, previous_version_id, action, success,
                  actor_user_id, details
                ) values (
                  cast(:model_version_id as uuid), cast(:previous_version_id as uuid),
                  'deploy', false, :actor, cast(:details as jsonb)
                )
                """
            ),
            {
                "model_version_id": row["id"],
                "previous_version_id": previous.get("id") if previous else None,
                "actor": str(actor.id),
                "details": json.dumps({"error": str(error)}),
            },
        )
        db.session.commit()
        raise ModelRegistryError(
            f"Deployment failed; production model left unchanged. {error}",
            503,
        ) from error


def reject_candidate(actor: OwnerUser, version_id: str) -> dict[str, Any]:
    row = db.session.execute(
        text(
            """
            select id::text as id, version_label, is_production, status
            from public.model_versions where id::text = :id limit 1
            """
        ),
        {"id": version_id},
    ).mappings().first()
    if not row:
        raise ModelRegistryError("Candidate not found.", 404)
    if row["is_production"]:
        raise ModelRegistryError("Cannot reject the active production model.")
    db.session.execute(
        text(
            """
            update public.model_versions
            set status = 'rejected', updated_at = timezone('utc', now())
            where id = cast(:id as uuid)
            """
        ),
        {"id": version_id},
    )
    db.session.execute(
        text(
            """
            insert into public.model_deployments (
              model_version_id, action, success, actor_user_id, details
            ) values (
              cast(:id as uuid), 'reject', true, :actor, '{}'::jsonb
            )
            """
        ),
        {"id": version_id, "actor": str(actor.id)},
    )
    db.session.commit()
    return {"ok": True, "message": f"Rejected candidate {row['version_label']}."}


def rollback_production(actor: OwnerUser) -> dict[str, Any]:
    production = get_production_model()
    if not production:
        raise ModelRegistryError("No production model is registered.")
    previous = db.session.execute(
        text(
            """
            select id::text as id, version_label, artifact_dir, status
            from public.model_versions
            where id <> cast(:current as uuid)
              and artifact_dir is not null
            order by
              case when deployed_at is not null then 0 else 1 end,
              deployed_at desc nulls last,
              version_number desc
            limit 1
            """
        ),
        {"current": production["id"]},
    ).mappings().first()
    if not previous:
        raise ModelRegistryError("No previous version available for rollback.")

    # Mark previous as evaluation_passed so deploy_candidate accepts it.
    db.session.execute(
        text(
            """
            update public.model_versions
            set status = 'evaluation_passed', updated_at = timezone('utc', now())
            where id = cast(:id as uuid)
            """
        ),
        {"id": previous["id"]},
    )
    db.session.commit()
    result = deploy_candidate(actor, previous["id"])
    db.session.execute(
        text(
            """
            insert into public.model_deployments (
              model_version_id, previous_version_id, action, success,
              actor_user_id, details
            ) values (
              cast(:model_version_id as uuid), cast(:previous_version_id as uuid),
              'rollback', true, :actor, cast(:details as jsonb)
            )
            """
        ),
        {
            "model_version_id": previous["id"],
            "previous_version_id": production["id"],
            "actor": str(actor.id),
            "details": json.dumps({"rolled_back_from": production["version_label"]}),
        },
    )
    db.session.commit()
    result["message"] = (
        f"Rolled back to {previous['version_label']}. "
        f"Previous production {production['version_label']} was archived."
    )
    return result


def read_training_log(version_id: str | None = None, max_lines: int = 200) -> str:
    candidate = None
    if version_id:
        candidate = db.session.execute(
            text(
                "select artifact_dir from public.model_versions where id::text = :id limit 1"
            ),
            {"id": version_id},
        ).mappings().first()
    else:
        candidate = get_latest_candidate()
    if not candidate or not candidate.get("artifact_dir"):
        return "No training log available."
    log_path = Path(candidate["artifact_dir"]) / "training.log"
    if not log_path.is_file():
        return "Training log file not found yet."
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])
