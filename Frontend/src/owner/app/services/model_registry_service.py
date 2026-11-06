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


def _resolve_training_target(
    *,
    new_major: bool,
    production: dict[str, Any] | None,
) -> tuple[int, int, str, dict[str, Any] | None]:
    """Return (major, revision, display, reuse_row).

    Cancel / reject / failed candidates are reused in-place (same vN.r) so retries
    do not create v1.3, v1.4, … and orphan weight files. A new revision number is
    allocated only when starting a new major, or when the current major has no
    replaceable non-production candidate (e.g. production is already v1.2).
    """
    if new_major:
        max_major = int(
            db.session.execute(
                text("select coalesce(max(major_version), 0)::int from public.model_versions")
            ).scalar()
            or 0
        )
        major = max(max_major, int((production or {}).get("major_version") or 0)) + 1
        revision = 1
        return major, revision, _display_revision(major, revision), None

    major = int((production or {}).get("major_version") or 1)
    # Reuse failed/rejected/cancelled slots only. Never overwrite a previously
    # deployed archived revision (needed for Restore).
    replaceable = db.session.execute(
        text(
            """
            select
              id::text as id,
              version_label,
              artifact_dir,
              status,
              coalesce(major_version, 1)::int as major_version,
              coalesce(revision_number, 1)::int as revision_number
            from public.model_versions
            where major_version = :major
              and is_production = false
              and deployed_at is null
              and status in (
                'failed', 'evaluation_failed', 'rejected', 'cancelled'
              )
            order by revision_number desc, updated_at desc nulls last
            limit 1
            """
        ),
        {"major": major},
    ).mappings().first()
    if replaceable:
        revision = int(replaceable["revision_number"])
        return (
            major,
            revision,
            _display_revision(major, revision),
            dict(replaceable),
        )

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
    prod_rev = int((production or {}).get("revision_number") or 0)
    revision = max(max_rev, prod_rev) + 1
    if revision <= 1 and not production:
        major = 1
        revision = 1
    return major, revision, _display_revision(major, revision), None


def _stable_artifact_dir(major: int, revision: int) -> Path:
    """Stable folder per revision so retries overwrite instead of stacking copies."""
    return REGISTRY_ROOT / f"v{int(major)}_{int(revision)}"


def _reset_artifact_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


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
                  to_char(deployed_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC') as deployed_at,
                  (deployed_at is not null) as was_deployed
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
            art = Path(item.get("artifact_dir") or "")
            item["can_restore"] = bool(
                not item.get("is_production")
                and item.get("was_deployed")
                and (art / "main_classifier.keras").is_file()
                and (art / "labels.json").is_file()
            )
            items.append(item)
        return items
    except SQLAlchemyError:
        db.session.rollback()
        return []


# Candidate still needs Owner action before another train can start.
_ACTIVE_CANDIDATE_STATUSES = {
    "training",
    "queued",
    "pending_evaluation",
    "evaluation_passed",
    "approved_for_deployment",
}
# Safe to start a new revision after these.
_TERMINAL_CANDIDATE_STATUSES = {
    "failed",
    "evaluation_failed",
    "rejected",
    "archived",
    "cancelled",
}


def get_latest_candidate() -> dict[str, Any] | None:
    """Prefer the newest actionable candidate; otherwise show the latest archived/rejected one."""
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
                order by
                  case
                    when v.status in (
                      'training', 'queued', 'pending_evaluation',
                      'evaluation_passed', 'approved_for_deployment'
                    ) then 0
                    when v.status in ('failed', 'evaluation_failed') then 1
                    else 2
                  end,
                  v.major_version desc nulls last,
                  v.revision_number desc nulls last
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


def _cancel_training_jobs_for_version(
    version_id: str,
    *,
    reason: str = "Cancelled because the candidate was rejected.",
) -> int:
    """Mark queued/running jobs cancelled and best-effort stop the worker process."""
    rows = db.session.execute(
        text(
            """
            select id::text as id, pid
            from public.training_jobs
            where model_version_id = cast(:version_id as uuid)
              and status in ('queued', 'running')
            """
        ),
        {"version_id": version_id},
    ).mappings().all()
    for row in rows:
        pid = row.get("pid")
        if pid:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    os.kill(int(pid), 15)
            except OSError:
                pass
        db.session.execute(
            text(
                """
                update public.training_jobs
                set status = 'cancelled',
                    finished_at = timezone('utc', now()),
                    progress_message = :reason,
                    error_message = :reason,
                    updated_at = timezone('utc', now())
                where id = cast(:id as uuid)
                """
            ),
            {"id": row["id"], "reason": reason[:500]},
        )
    return len(rows)


def _pid_is_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {int(pid)}"],
                capture_output=True,
                text=True,
                check=False,
            )
            return str(pid) in (result.stdout or "")
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def reconcile_stale_training_jobs() -> int:
    """Clear stuck jobs (dead process or terminal candidate) so retraining is possible."""
    try:
        rows = db.session.execute(
            text(
                """
                select j.id::text as id, j.pid, v.id::text as version_id, v.status as version_status
                from public.training_jobs j
                join public.model_versions v on v.id = j.model_version_id
                where j.status in ('queued', 'running')
                """
            )
        ).mappings().all()
        cleared = 0
        for row in rows:
            terminal = row["version_status"] in _TERMINAL_CANDIDATE_STATUSES
            dead = not _pid_is_alive(row.get("pid"))
            prod = False
            if terminal or dead:
                reason = (
                    f"Auto-cleared stale job; candidate status is {row['version_status']}."
                    if terminal
                    else "Auto-cleared stale job; training process is no longer running."
                )
                if dead and not terminal and row["version_status"] == "training":
                    db.session.execute(
                        text(
                            """
                            update public.model_versions
                            set status = 'failed',
                                updated_at = timezone('utc', now())
                            where id = cast(:id as uuid)
                              and status = 'training'
                            """
                        ),
                        {"id": row["version_id"]},
                    )
                cleared += _cancel_training_jobs_for_version(
                    row["version_id"], reason=reason
                )
            _ = prod
        if cleared:
            db.session.commit()
        return cleared
    except SQLAlchemyError:
        db.session.rollback()
        return 0


def get_active_training_job() -> dict[str, Any] | None:
    try:
        reconcile_stale_training_jobs()
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
                  and v.status not in ('rejected', 'archived')
                  and v.is_production = false
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
    last_trainable = 0
    if candidate:
        summary = candidate.get("dataset_summary") or {}
        if isinstance(summary, str):
            try:
                summary = json.loads(summary or "{}")
            except json.JSONDecodeError:
                summary = {}
        last_trainable = int(summary.get("trainable_contribution_count") or 0)
    current_trainable = int(dataset.get("trainable_contribution_count") or 0)
    new_since_last_revision = max(0, current_trainable - last_trainable)

    cand_status = (candidate or {}).get("status")
    has_blocking_candidate = bool(
        candidate and cand_status in _ACTIVE_CANDIDATE_STATUSES
    )
    can_start = active_job is None and not has_blocking_candidate
    previous_production = None
    if production:
        previous_production = db.session.execute(
            text(
                """
                select id::text as id, version_label, artifact_dir
                from public.model_versions
                where id <> cast(:current as uuid)
                  and deployed_at is not null
                  and artifact_dir is not null
                order by deployed_at desc nulls last
                limit 1
                """
            ),
            {"current": production["id"]},
        ).mappings().first()

    can_retry = bool(
        can_start and candidate and cand_status in _TERMINAL_CANDIDATE_STATUSES
    )
    can_evaluate = bool(
        candidate
        and cand_status
        in {
            "pending_evaluation",
            "evaluation_passed",
            "evaluation_failed",
            "approved_for_deployment",
        }
    )
    can_deploy = bool(
        candidate and cand_status in {"evaluation_passed", "approved_for_deployment"}
    )
    can_reject = bool(
        candidate
        and not candidate.get("is_production")
        and cand_status not in {"rejected", "archived", "active"}
    )
    can_rollback = bool(previous_production)
    can_view_logs = bool(
        candidate and (candidate.get("artifact_dir") or candidate.get("job_id"))
    )
    can_cancel = bool(active_job and candidate and can_reject)

    display_cand = (
        (candidate or {}).get("display_revision")
        or (candidate or {}).get("version_label")
        or "candidate"
    )
    if active_job:
        start_block = (
            "Training is already running. Wait for it to finish, or Cancel Training."
        )
    elif has_blocking_candidate:
        start_block = (
            f"{display_cand} is still '{cand_status}'. "
            "Deploy it or Reject it before starting another training run."
        )
    else:
        start_block = ""

    # Lifecycle stepper for Owner guidance.
    if active_job or cand_status == "training":
        step_key = "train"
    elif cand_status in {"pending_evaluation", "evaluation_passed", "approved_for_deployment"}:
        step_key = "deploy" if can_deploy else "evaluate"
    elif cand_status in _TERMINAL_CANDIDATE_STATUSES:
        step_key = "dataset"
    elif int(dataset.get("added_to_dataset") or 0) > 0 or current_trainable > 0:
        step_key = "train"
    else:
        step_key = "dataset"
    lifecycle_steps = [
        {
            "key": "dataset",
            "label": "1. Dataset",
            "detail": "Approve + Add to Dataset",
            "active": step_key == "dataset",
        },
        {
            "key": "train",
            "label": "2. Train",
            "detail": "Train next revision",
            "active": step_key == "train",
        },
        {
            "key": "evaluate",
            "label": "3. Evaluate",
            "detail": "Auto-eval after train",
            "active": step_key == "evaluate",
        },
        {
            "key": "deploy",
            "label": "4. Deploy",
            "detail": "Approve and go live",
            "active": step_key == "deploy",
        },
    ]

    button_notes = {
        "start_train": (
            ""
            if can_start
            else start_block or "Training cannot start right now."
        ),
        "start_major": (
            ""
            if can_start
            else start_block or "A new major version cannot start right now."
        ),
        "retry": (
            ""
            if can_retry
            else (
                start_block
                if not can_start
                else "Retry is only for failed, rejected, or archived candidates. Use Train Next Revision for a fresh run."
            )
        ),
        "evaluate": (
            ""
            if can_evaluate
            else (
                "No candidate metrics yet. Start training and wait until it finishes (auto-evaluation runs after training)."
                if not candidate
                else f"{display_cand} status is '{cand_status}'. Re-evaluate is available after training finishes."
            )
        ),
        "deploy": (
            ""
            if can_deploy
            else (
                "Nothing to deploy yet. Train a candidate and wait until evaluation passes."
                if not candidate
                else f"{display_cand} status is '{cand_status}'. Deploy unlocks only after evaluation passes."
            )
        ),
        "reject": (
            ""
            if can_reject
            else (
                "No active candidate to reject."
                if not candidate
                else f"{display_cand} is already '{cand_status}' and cannot be rejected again."
            )
        ),
        "cancel": (
            ""
            if can_cancel
            else "Cancel is only available while a training job is running."
        ),
        "rollback": (
            ""
            if can_rollback
            else "Restore needs a previously deployed production revision. Deploy at least one newer model first."
        ),
        "view_logs": (
            ""
            if can_view_logs
            else "No training logs yet. Start a training run first."
        ),
        "restore_version": (
            "Choose an archived previously-deployed revision from Model history."
        ),
    }

    preview_label = "v1.2"
    will_reuse = False
    if production:
        _maj, _rev, preview_label, reuse_row = _resolve_training_target(
            new_major=False, production=production
        )
        will_reuse = reuse_row is not None

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
        # One active candidate at a time: Deploy or Reject before starting another.
        "can_start_training": can_start,
        "can_retry": can_retry,
        "can_evaluate": can_evaluate,
        "can_deploy": can_deploy,
        "can_reject": can_reject,
        "can_cancel": can_cancel,
        "can_rollback": can_rollback,
        "can_view_logs": can_view_logs,
        "button_notes": button_notes,
        "lifecycle_steps": lifecycle_steps,
        "lifecycle_step": step_key,
        "previous_production_label": (
            (previous_production or {}).get("version_label") if previous_production else None
        ),
        "workflow_hint": (
            "Training in progress - wait, view logs, or Cancel Training."
            if active_job
            else (
                "Candidate ready - Approve and Deploy, or Reject to train again."
                if cand_status
                in {
                    "pending_evaluation",
                    "evaluation_passed",
                    "approved_for_deployment",
                }
                else (
                    "Candidate closed - Train / Retry reuses the same revision number (e.g. stays v1.2) and refreshes weights."
                    if cand_status in _TERMINAL_CANDIDATE_STATUSES
                    else "Approve photos, Add to Dataset, then Train. Cancel/retry keeps the same revision slot to save disk."
                )
            )
        ),
        "last_revision_trainable_count": last_trainable,
        "new_images_since_last_revision": new_since_last_revision,
        "next_revision_preview": preview_label,
        "will_reuse_revision": will_reuse,
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
        existing = get_latest_candidate()
        if existing and existing.get("status") in _ACTIVE_CANDIDATE_STATUSES:
            raise ModelRegistryError(
                f"Candidate {existing.get('display_revision') or existing.get('version_label')} "
                f"is still {existing.get('status')}. Deploy it or Reject it before starting another training run.",
                409,
            )

        production = get_production_model()
        major, revision, display, reuse_row = _resolve_training_target(
            new_major=new_major, production=production
        )
        reused = reuse_row is not None
        version_label = display
        artifact_dir = _stable_artifact_dir(major, revision)
        # Drop previous failed/rejected weights for this revision slot (saves disk).
        if reused and reuse_row.get("artifact_dir"):
            old_dir = Path(reuse_row["artifact_dir"])
            if old_dir.resolve() != artifact_dir.resolve() and old_dir.exists():
                shutil.rmtree(old_dir, ignore_errors=True)
        _reset_artifact_dir(artifact_dir)
        # Candidate-only path — never writes into live production keras files.
        (artifact_dir / "CANDIDATE_ONLY.txt").write_text(
            "Independent candidate artifact. Production inference uses app model files until deploy.\n"
            f"Revision slot {display} is reused on cancel/retry to avoid extra versions.\n",
            encoding="utf-8",
        )
        dataset = _build_dataset_snapshot(
            major=major, revision=revision, production=production
        )
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
                    "reuse_revision": reused,
                    "contributions": dataset.get("contributions") or [],
                    "newly_added_since_production": dataset.get(
                        "newly_added_since_production"
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        dataset_for_db = {
            k: v for k, v in dataset.items() if k != "contributions"
        }
        notes = (
            "retry_same_revision"
            if reused or retry
            else ("new_major" if new_major else "revision_under_current_major")
        )

        if reused:
            _cancel_training_jobs_for_version(
                reuse_row["id"],
                reason="Superseded by a same-revision retrain.",
            )
            version = db.session.execute(
                text(
                    """
                    update public.model_versions
                    set version_label = :version_label,
                        status = 'training',
                        artifact_dir = :artifact_dir,
                        parent_version_id = cast(:parent_id as uuid),
                        is_production = false,
                        metrics_json = '{}'::jsonb,
                        dataset_summary = cast(:dataset_summary as jsonb),
                        dataset_snapshot_id = :snapshot_id,
                        notes = :notes,
                        updated_at = timezone('utc', now())
                    where id = cast(:id as uuid)
                    returning id::text as id, version_label, version_number,
                              major_version, revision_number, status, artifact_dir
                    """
                ),
                {
                    "id": reuse_row["id"],
                    "version_label": version_label,
                    "artifact_dir": str(artifact_dir),
                    "parent_id": production.get("id") if production else None,
                    "dataset_summary": json.dumps(dataset_for_db),
                    "snapshot_id": dataset["snapshot_id"],
                    "notes": notes,
                },
            ).mappings().first()
        else:
            next_number = int(
                db.session.execute(
                    text(
                        "select coalesce(max(version_number), 0)::int + 1 from public.model_versions"
                    )
                ).scalar()
                or 1
            )
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
                    "notes": notes,
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
            "reused_revision": reused,
            "message": (
                f"{'Reusing' if reused else 'Started'} training revision {display} "
                f"{'(same slot — no new version number)' if reused else 'in the background'}. "
                f"Production remains on "
                f"{(production or {}).get('display_revision') or (production or {}).get('version_label') or 'current'}. "
                "Live production weights were not overwritten."
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
            select id::text as id, version_label, is_production, status,
                   coalesce(major_version, version_number, 1)::int as major_version,
                   coalesce(revision_number, 1)::int as revision_number
            from public.model_versions where id::text = :id limit 1
            """
        ),
        {"id": version_id},
    ).mappings().first()
    if not row:
        raise ModelRegistryError("Candidate not found.", 404)
    if row["is_production"]:
        raise ModelRegistryError("Cannot reject the active production model.")
    # Keep artifacts for history; stop any worker so Train Next Revision can run.
    cancelled = _cancel_training_jobs_for_version(
        version_id,
        reason="Cancelled because the Owner rejected this candidate.",
    )
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
              cast(:id as uuid), 'reject', true, :actor, cast(:details as jsonb)
            )
            """
        ),
        {
            "id": version_id,
            "actor": str(actor.id),
            "details": json.dumps({"cancelled_jobs": cancelled}),
        },
    )
    db.session.commit()
    display = _display_revision(row["major_version"], row["revision_number"])
    return {
        "ok": True,
        "message": (
            f"Rejected {display}. Artifacts kept in history. "
            "Use Train Next Revision (or Retry Training) to train again; "
            "the next run will include the current dataset pool, including any newly added batches."
        ),
    }


def restore_version(actor: OwnerUser, version_id: str) -> dict[str, Any]:
    """Restore any previously deployed archived revision to production."""
    production = get_production_model()
    if not production:
        raise ModelRegistryError("No production model is registered.")
    target = db.session.execute(
        text(
            """
            select id::text as id, version_label, artifact_dir, status, is_production,
                   deployed_at,
                   coalesce(major_version, version_number, 1)::int as major_version,
                   coalesce(revision_number, 1)::int as revision_number
            from public.model_versions
            where id::text = :id
            limit 1
            """
        ),
        {"id": version_id},
    ).mappings().first()
    if not target:
        raise ModelRegistryError("Version not found.", 404)
    if target["is_production"]:
        raise ModelRegistryError("That revision is already the live production model.")
    if not target.get("deployed_at"):
        raise ModelRegistryError(
            "Only previously deployed revisions can be restored. "
            "Rejected unfinished candidates cannot be restored — train a new revision instead."
        )
    artifact_dir = Path(target["artifact_dir"] or "")
    if not (artifact_dir / "main_classifier.keras").is_file():
        raise ModelRegistryError("Restore artifacts are missing.", 400)
    if not (artifact_dir / "labels.json").is_file():
        raise ModelRegistryError("Restore labels are missing.", 400)

    # If a candidate is mid-flight, reject/cancel it first so only one active path exists.
    candidate = get_latest_candidate()
    if (
        candidate
        and candidate.get("id") != target["id"]
        and candidate.get("status") in _ACTIVE_CANDIDATE_STATUSES
    ):
        reject_candidate(actor, candidate["id"])

    db.session.execute(
        text(
            """
            update public.model_versions
            set status = 'evaluation_passed', updated_at = timezone('utc', now())
            where id = cast(:id as uuid)
            """
        ),
        {"id": target["id"]},
    )
    db.session.commit()
    result = deploy_candidate(actor, target["id"])
    db.session.execute(
        text(
            """
            insert into public.model_deployments (
              model_version_id, previous_version_id, action, success,
              actor_user_id, details
            ) values (
              cast(:model_version_id as uuid), cast(:previous_version_id as uuid),
              'restore', true, :actor, cast(:details as jsonb)
            )
            """
        ),
        {
            "model_version_id": target["id"],
            "previous_version_id": production["id"],
            "actor": str(actor.id),
            "details": json.dumps(
                {
                    "restored_from": production["version_label"],
                    "restored_to": target["version_label"],
                }
            ),
        },
    )
    db.session.commit()
    display = _display_revision(target["major_version"], target["revision_number"])
    result["message"] = (
        f"Restored {display} to production. "
        f"Previous live model {production.get('display_revision') or production['version_label']} was archived."
    )
    return result


def rollback_production(actor: OwnerUser) -> dict[str, Any]:
    """Restore the most recently deployed non-current production revision."""
    production = get_production_model()
    if not production:
        raise ModelRegistryError("No production model is registered.")
    previous = db.session.execute(
        text(
            """
            select id::text as id, version_label
            from public.model_versions
            where id <> cast(:current as uuid)
              and deployed_at is not null
              and artifact_dir is not null
            order by deployed_at desc nulls last
            limit 1
            """
        ),
        {"current": production["id"]},
    ).mappings().first()
    if not previous:
        raise ModelRegistryError(
            "No previously deployed production revision is available to restore yet."
        )
    result = restore_version(actor, previous["id"])
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
