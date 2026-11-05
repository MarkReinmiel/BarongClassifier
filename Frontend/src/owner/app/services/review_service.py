"""Owner review of customer classifications for future dataset contributions.

Approval does NOT retrain or overwrite the production model.
"""

from __future__ import annotations

from typing import Any

from flask import current_app
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import OwnerUser

ALLOWED_STATUSES = frozenset(
    {"pending_review", "approved", "rejected", "uncertain", "added_to_dataset"}
)
ALLOWED_VERIFIED = frozenset({"pina", "jusi", "cocoon"})
DISPLAY = {
    "pina": "Piña",
    "jusi": "Jusi",
    "cocoon": "Cocoon",
    "undefined_textile": "Undefined Textile",
    "uncertain": "Uncertain",
    "poor_image_quality": "Poor Image Quality",
}


class ReviewError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def display_label(raw: str | None) -> str:
    key = (raw or "").strip().lower().replace("ñ", "n")
    if "undefined" in key:
        return DISPLAY["undefined_textile"]
    if key in DISPLAY:
        return DISPLAY[key]
    if "pina" in key or "piña" in (raw or "").lower():
        return "Piña"
    if "jusi" in key:
        return "Jusi"
    if "cocoon" in key:
        return "Cocoon"
    return (raw or "—").strip() or "—"


def _normalize_verified(label: str | None) -> str:
    key = (label or "").strip().lower().replace("ñ", "n")
    if key in {"piña", "pineapple"}:
        key = "pina"
    if key not in ALLOWED_VERIFIED:
        raise ReviewError("Verified label must be Piña, Jusi, or Cocoon.")
    return key


def contribution_counts() -> dict[str, int]:
    empty = {
        "pending_review": 0,
        "approved": 0,
        "rejected": 0,
        "uncertain": 0,
        "added_to_dataset": 0,
        "approved_panel": 0,
        "total_classifications": 0,
    }
    if current_app.config.get("TESTING"):
        return empty
    try:
        total = db.session.execute(
            text("select count(*)::int from public.classifications")
        ).scalar() or 0
        reviewed = db.session.execute(
            text(
                """
                select review_status, count(*)::int as n
                from public.classification_reviews
                group by review_status
                """
            )
        ).mappings().all()
        counts = dict(empty)
        counts["total_classifications"] = int(total)
        for row in reviewed:
            status = row["review_status"]
            n = int(row["n"] or 0)
            if status in counts:
                counts[status] = n
        decided = sum(
            counts[s] for s in ("approved", "rejected", "uncertain", "added_to_dataset")
        )
        counts["pending_review"] = max(0, int(total) - decided)
        # Approved panel includes suitability-approved + dataset-pool items.
        counts["approved_panel"] = int(counts["approved"]) + int(
            counts["added_to_dataset"]
        )
        return counts
    except SQLAlchemyError:
        db.session.rollback()
        return empty


def list_customer_classifications(
    *,
    page: int = 1,
    per_page: int = 12,
    q: str | None = None,
    fabric: str | None = None,
    review_status: str | None = None,
    panel: str | None = None,
    date_preset: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str = "newest",
) -> dict[str, Any]:
    empty = {
        "items": [],
        "total": 0,
        "page": 1,
        "pages": 1,
        "per_page": per_page,
        "counts": contribution_counts(),
    }
    if current_app.config.get("TESTING"):
        return empty

    page = max(1, int(page or 1))
    per_page = min(50, max(1, int(per_page or 12)))
    clauses = ["1=1"]
    params: dict[str, Any] = {"limit": per_page, "offset": (page - 1) * per_page}

    preset = (date_preset or "").strip().lower()
    if preset == "today":
        clauses.append("c.created_at::date = (timezone('utc', now()))::date")
    elif preset in {"7d", "last_7_days"}:
        clauses.append("c.created_at >= timezone('utc', now()) - interval '7 days'")
    elif preset in {"30d", "last_30_days"}:
        clauses.append("c.created_at >= timezone('utc', now()) - interval '30 days'")
    if date_from:
        clauses.append("c.created_at::date >= cast(:date_from as date)")
        params["date_from"] = date_from
    if date_to:
        clauses.append("c.created_at::date <= cast(:date_to as date)")
        params["date_to"] = date_to

    if fabric:
        key = fabric.strip().lower().replace("ñ", "n")
        if key in {"undefined", "undefined_textile"}:
            clauses.append(
                """
                (
                  lower(coalesce(c.display_name, c.predicted_label, '')) like '%undefined%'
                  or lower(coalesce(c.predicted_label, '')) like '%undefined%'
                )
                """
            )
        elif key == "pina":
            clauses.append(
                "(lower(replace(coalesce(c.display_name, c.predicted_label), 'ñ', 'n')) like '%pina%')"
            )
        else:
            clauses.append(
                "lower(coalesce(c.display_name, c.predicted_label)) like :fabric_like"
            )
            params["fabric_like"] = f"%{key}%"

    if q:
        clauses.append(
            """
            (
              lower(coalesce(u.email, '')) like :q
              or lower(coalesce(u.full_name, '')) like :q
              or lower(coalesce(u.nickname, '')) like :q
            )
            """
        )
        params["q"] = f"%{q.strip().lower()}%"

    panel_key = (panel or "").strip().lower()
    if panel_key in {"pending", "pending_review"}:
        status_key = "pending_review"
    elif panel_key in {"approved", "approved_panel"}:
        status_key = "approved_panel"
    elif panel_key == "rejected":
        status_key = "rejected"
    else:
        status_key = (review_status or "").strip().lower()

    if status_key and status_key != "all":
        if status_key == "approved_panel":
            clauses.append("r.review_status in ('approved', 'added_to_dataset')")
        elif status_key not in ALLOWED_STATUSES:
            raise ReviewError("Invalid review status filter.")
        elif status_key == "pending_review":
            clauses.append(
                "(r.id is null or r.review_status = 'pending_review')"
            )
        else:
            clauses.append("r.review_status = :review_status")
            params["review_status"] = status_key

    order = "c.created_at asc nulls last" if sort == "oldest" else "c.created_at desc nulls last"
    where_sql = " and ".join(clauses)

    try:
        total = db.session.execute(
            text(
                f"""
                select count(*)::int
                from public.classifications c
                left join customer.users u on u.id = c.user_id::text
                left join public.classification_reviews r
                  on r.classification_id = c.id
                where {where_sql}
                """
            ),
            params,
        ).scalar() or 0
        pages = max(1, (int(total) + per_page - 1) // per_page)
        page = min(page, pages)
        params["offset"] = (page - 1) * per_page

        rows = db.session.execute(
            text(
                f"""
                select
                  c.id::text as id,
                  c.user_id::text as user_id,
                  coalesce(nullif(trim(u.full_name), ''), nullif(trim(u.nickname), ''), 'Customer')
                    as customer_name,
                  coalesce(u.email, '') as customer_email,
                  coalesce(c.display_name, c.predicted_label) as predicted_label,
                  c.predicted_label as predicted_label_raw,
                  c.confidence::float as confidence,
                  coalesce(c.file_name, '') as image_name,
                  case
                    when c.image_path like 'https://%' then c.image_path
                    when c.image_reference like 'https://%' then c.image_reference
                    else null
                  end as image_url,
                  to_char(c.created_at at time zone 'UTC', 'YYYY-MM-DD HH24:MI') as created_at,
                  to_char(c.created_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI') as created_at_display,
                  coalesce(r.review_status, 'pending_review') as review_status,
                  r.verified_label as verified_label,
                  r.rejection_reason as rejection_reason,
                  r.reviewed_by::text as reviewed_by,
                  to_char(r.reviewed_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI') as reviewed_at
                from public.classifications c
                left join customer.users u on u.id = c.user_id::text
                left join public.classification_reviews r
                  on r.classification_id = c.id
                where {where_sql}
                order by {order}
                limit :limit offset :offset
                """
            ),
            params,
        ).mappings().all()

        items = []
        for row in rows:
            item = dict(row)
            item["predicted_display"] = display_label(item.get("predicted_label"))
            item["verified_display"] = (
                display_label(item.get("verified_label"))
                if item.get("verified_label")
                else None
            )
            item["confidence_pct"] = round(float(item.get("confidence") or 0) * 100, 1)
            item["in_dataset_pool"] = item.get("review_status") == "added_to_dataset"
            item["selectable_for_review"] = (
                item.get("review_status") or "pending_review"
            ) == "pending_review"
            item["selectable_for_dataset"] = item.get("review_status") == "approved"
            items.append(item)

        return {
            "items": items,
            "total": int(total),
            "page": page,
            "pages": pages,
            "per_page": per_page,
            "counts": contribution_counts(),
        }
    except SQLAlchemyError as error:
        db.session.rollback()
        current_app.logger.exception("list_customer_classifications failed")
        raise ReviewError("Could not load classification history.", 503) from error


def get_classification_detail(classification_id: str) -> dict[str, Any]:
    if current_app.config.get("TESTING"):
        raise ReviewError("Not available in tests.", 404)
    try:
        row = db.session.execute(
            text(
                """
                select
                  c.id::text as id,
                  c.user_id::text as user_id,
                  coalesce(nullif(trim(u.full_name), ''), nullif(trim(u.nickname), ''), 'Customer')
                    as customer_name,
                  coalesce(u.email, '') as customer_email,
                  coalesce(c.display_name, c.predicted_label) as predicted_label,
                  c.predicted_label as predicted_label_raw,
                  c.confidence::float as confidence,
                  coalesce(c.file_name, '') as image_name,
                  case
                    when c.image_path like 'https://%' then c.image_path
                    when c.image_reference like 'https://%' then c.image_reference
                    else null
                  end as image_url,
                  to_char(c.created_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC') as created_at_display,
                  coalesce(r.review_status, 'pending_review') as review_status,
                  r.verified_label as verified_label,
                  r.rejection_reason as rejection_reason,
                  r.notes as notes,
                  r.dataset_version as dataset_version,
                  r.reviewed_by::text as reviewed_by,
                  to_char(r.reviewed_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC') as reviewed_at,
                  r.id::text as review_id
                from public.classifications c
                left join customer.users u on u.id = c.user_id::text
                left join public.classification_reviews r on r.classification_id = c.id
                where c.id::text = :id
                limit 1
                """
            ),
            {"id": str(classification_id)},
        ).mappings().first()
        if not row:
            raise ReviewError("Classification was not found.", 404)

        events = db.session.execute(
            text(
                """
                select
                  e.action,
                  e.previous_status,
                  e.new_status,
                  e.verified_label,
                  e.rejection_reason,
                  e.actor_user_id::text as actor_user_id,
                  coalesce(ou.email, e.actor_user_id::text) as actor_email,
                  to_char(e.created_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI UTC') as created_at
                from public.classification_review_events e
                left join customer.users ou on ou.id = e.actor_user_id::text
                where e.classification_id::text = :id
                order by e.created_at desc
                limit 50
                """
            ),
            {"id": str(classification_id)},
        ).mappings().all()

        detail = dict(row)
        detail["predicted_display"] = display_label(detail.get("predicted_label"))
        detail["verified_display"] = (
            display_label(detail.get("verified_label"))
            if detail.get("verified_label")
            else None
        )
        detail["confidence_pct"] = round(float(detail.get("confidence") or 0) * 100, 1)
        detail["events"] = [dict(e) for e in events]
        # Approved = suitable photo for future dataset work.
        # Class assignment (Piña/Jusi/Cocoon folders) requires a separate labeling step.
        detail["eligible_for_dataset"] = detail.get("review_status") in {
            "approved",
            "added_to_dataset",
        }
        detail["labeled_for_training"] = bool(detail.get("verified_label")) and detail[
            "eligible_for_dataset"
        ]
        return detail
    except ReviewError:
        raise
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ReviewError("Could not load classification details.", 503) from error


def submit_review(
    actor: OwnerUser,
    classification_id: str,
    *,
    action: str,
    verified_label: str | None = None,
    rejection_reason: str | None = None,
    notes: str | None = None,
    confirm_change: bool = False,
) -> dict[str, Any]:
    action_key = (action or "").strip().lower()
    status_map = {
        "approve": "approved",
        "approved": "approved",
        "reject": "rejected",
        "rejected": "rejected",
        "uncertain": "uncertain",
        "mark_uncertain": "uncertain",
        "added_to_dataset": "added_to_dataset",
    }
    if action_key not in status_map:
        raise ReviewError("Action must be approve, reject, or uncertain.")
    new_status = status_map[action_key]

    # Simplified Owner review: approve/reject photo suitability only.
    # Do not require or invent a verified textile class from the CNN prediction.
    # rejection_reason is intentionally ignored for this workflow.
    verified = None
    reason = None
    note = (notes or "").strip() or None
    _ = rejection_reason  # kept in signature for API compatibility
    if verified_label:
        # Optional legacy path if a separate labeling tool still sends a label.
        try:
            verified = _normalize_verified(verified_label)
        except ReviewError:
            verified = None

    if current_app.config.get("TESTING"):
        raise ReviewError("Not available in tests.", 400)

    try:
        detail = get_classification_detail(classification_id)
        previous = detail.get("review_status") or "pending_review"

        if previous not in {"pending_review", new_status} and not confirm_change:
            raise ReviewError(
                "This record was already reviewed. Confirm the change to overwrite "
                "the previous decision (audit history is preserved).",
                409,
            )

        if new_status == "added_to_dataset" and previous not in {
            "approved",
            "added_to_dataset",
        }:
            raise ReviewError("Only approved images can be marked added_to_dataset.")

        if new_status == "added_to_dataset":
            # Keep any separately verified label if present; do not invent one.
            verified = detail.get("verified_label") or verified

        image_url = detail.get("image_url")
        # Clear verified_label on reject/uncertain so CNN prediction is never treated as ground truth.
        store_verified = verified if new_status in {"approved", "added_to_dataset"} else None
        upsert = db.session.execute(
            text(
                """
                insert into public.classification_reviews (
                  classification_id,
                  customer_user_id,
                  image_url,
                  predicted_label,
                  predicted_confidence,
                  verified_label,
                  review_status,
                  rejection_reason,
                  reviewed_by,
                  reviewed_at,
                  notes,
                  updated_at
                ) values (
                  cast(:classification_id as uuid),
                  :customer_user_id,
                  :image_url,
                  :predicted_label,
                  :predicted_confidence,
                  :verified_label,
                  :review_status,
                  :rejection_reason,
                  :reviewed_by,
                  timezone('utc', now()),
                  :notes,
                  timezone('utc', now())
                )
                on conflict (classification_id) do update set
                  image_url = excluded.image_url,
                  predicted_label = excluded.predicted_label,
                  predicted_confidence = excluded.predicted_confidence,
                  verified_label = excluded.verified_label,
                  review_status = excluded.review_status,
                  rejection_reason = excluded.rejection_reason,
                  reviewed_by = excluded.reviewed_by,
                  reviewed_at = excluded.reviewed_at,
                  notes = excluded.notes,
                  updated_at = timezone('utc', now())
                returning id::text as id
                """
            ),
            {
                "classification_id": str(classification_id),
                "customer_user_id": detail.get("user_id"),
                "image_url": image_url,
                "predicted_label": detail.get("predicted_label_raw")
                or detail.get("predicted_label"),
                "predicted_confidence": detail.get("confidence"),
                "verified_label": store_verified,
                "review_status": new_status,
                "rejection_reason": reason,
                "reviewed_by": str(actor.id),
                "notes": note,
            },
        ).mappings().first()

        review_id = upsert["id"] if upsert else None
        db.session.execute(
            text(
                """
                insert into public.classification_review_events (
                  classification_id,
                  review_id,
                  action,
                  previous_status,
                  new_status,
                  verified_label,
                  rejection_reason,
                  actor_user_id
                ) values (
                  cast(:classification_id as uuid),
                  cast(:review_id as uuid),
                  :action,
                  :previous_status,
                  :new_status,
                  :verified_label,
                  :rejection_reason,
                  :actor_user_id
                )
                """
            ),
            {
                "classification_id": str(classification_id),
                "review_id": review_id,
                "action": action_key,
                "previous_status": previous,
                "new_status": new_status,
                "verified_label": store_verified,
                "rejection_reason": reason,
                "actor_user_id": str(actor.id),
            },
        )
        db.session.commit()
        return get_classification_detail(classification_id)
    except ReviewError:
        db.session.rollback()
        raise
    except SQLAlchemyError as error:
        db.session.rollback()
        current_app.logger.exception("submit_review failed")
        raise ReviewError("Could not save review decision.", 503) from error


def list_approved_contributions(
    *,
    page: int = 1,
    per_page: int = 24,
    verified_label: str | None = None,
) -> dict[str, Any]:
    empty = {"items": [], "total": 0, "page": 1, "pages": 1, "per_page": per_page}
    if current_app.config.get("TESTING"):
        return empty
    page = max(1, int(page or 1))
    per_page = min(100, max(1, int(per_page or 24)))
    clauses = ["r.review_status in ('approved', 'added_to_dataset')"]
    params: dict[str, Any] = {"limit": per_page, "offset": (page - 1) * per_page}
    if verified_label:
        clauses.append("r.verified_label = :verified_label")
        params["verified_label"] = _normalize_verified(verified_label)
    where_sql = " and ".join(clauses)
    try:
        total = db.session.execute(
            text(
                f"""
                select count(*)::int
                from public.classification_reviews r
                where {where_sql}
                """
            ),
            params,
        ).scalar() or 0
        pages = max(1, (int(total) + per_page - 1) // per_page)
        page = min(page, pages)
        params["offset"] = (page - 1) * per_page
        rows = db.session.execute(
            text(
                f"""
                select
                  r.classification_id::text as id,
                  r.image_url,
                  r.verified_label,
                  r.predicted_label,
                  r.predicted_confidence::float as confidence,
                  r.review_status,
                  coalesce(nullif(trim(u.full_name), ''), nullif(trim(u.nickname), ''), 'Customer')
                    as customer_name,
                  coalesce(u.email, '') as customer_email,
                  to_char(r.reviewed_at at time zone 'UTC', 'Mon DD, YYYY') as reviewed_at
                from public.classification_reviews r
                left join customer.users u on u.id = r.customer_user_id
                where {where_sql}
                order by r.reviewed_at desc nulls last
                limit :limit offset :offset
                """
            ),
            params,
        ).mappings().all()
        items = []
        for row in rows:
            item = dict(row)
            item["predicted_display"] = display_label(item.get("predicted_label"))
            item["verified_display"] = (
                display_label(item.get("verified_label"))
                if item.get("verified_label")
                else None
            )
            item["confidence_pct"] = round(float(item.get("confidence") or 0) * 100, 1)
            item["labeled_for_training"] = bool(item.get("verified_label"))
            items.append(item)
        return {
            "items": items,
            "total": int(total),
            "page": page,
            "pages": pages,
            "per_page": per_page,
            "counts": contribution_counts(),
        }
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ReviewError("Could not load approved contributions.", 503) from error


def _normalize_id_list(classification_ids: list[str] | None) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in classification_ids or []:
        cid = str(raw or "").strip()
        if not cid or cid in seen:
            continue
        seen.add(cid)
        ordered.append(cid)
    if not ordered:
        raise ReviewError("Select at least one photo.")
    if len(ordered) > 100:
        raise ReviewError("Too many selected photos (maximum 100 per batch).")
    return ordered


def submit_batch_review(
    actor: OwnerUser,
    classification_ids: list[str] | None,
    *,
    action: str,
) -> dict[str, Any]:
    """Approve or reject many pending classifications. Returns per-id results."""
    action_key = (action or "").strip().lower()
    if action_key not in {"approve", "approved", "reject", "rejected"}:
        raise ReviewError("Batch action must be approve or reject.")
    normalized_action = "approve" if action_key.startswith("approve") else "reject"
    ids = _normalize_id_list(classification_ids)

    results: list[dict[str, Any]] = []
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []

    for classification_id in ids:
        try:
            detail = get_classification_detail(classification_id)
            previous = detail.get("review_status") or "pending_review"
            if previous != "pending_review":
                raise ReviewError(
                    f"Record is {previous.replace('_', ' ')}, not pending review."
                )
            item = submit_review(
                actor,
                classification_id,
                action=normalized_action,
                confirm_change=False,
            )
            results.append(
                {
                    "id": classification_id,
                    "ok": True,
                    "review_status": item.get("review_status"),
                    "item": item,
                }
            )
            succeeded.append(classification_id)
        except ReviewError as exc:
            entry = {"id": classification_id, "ok": False, "error": str(exc)}
            results.append(entry)
            failed.append({"id": classification_id, "error": str(exc)})
            current_app.logger.warning(
                "batch_review item failed action=%s id=%s error=%s",
                normalized_action,
                classification_id,
                exc,
            )

    return {
        "ok": len(failed) == 0,
        "action": normalized_action,
        "requested": len(ids),
        "succeeded_count": len(succeeded),
        "failed_count": len(failed),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
        "counts": contribution_counts(),
    }


def add_to_dataset_pool(
    actor: OwnerUser,
    classification_ids: list[str] | None,
) -> dict[str, Any]:
    """Move approved photos into the unlabeled dataset pool (added_to_dataset).

    Does not assign Piña/Jusi/Cocoon labels and does not retrain the model.
    """
    ids = _normalize_id_list(classification_ids)
    results: list[dict[str, Any]] = []
    succeeded: list[str] = []
    skipped: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []

    for classification_id in ids:
        try:
            detail = get_classification_detail(classification_id)
            previous = detail.get("review_status") or "pending_review"
            if previous == "added_to_dataset":
                skipped.append(
                    {
                        "id": classification_id,
                        "error": "Already in the dataset pool.",
                    }
                )
                results.append(
                    {
                        "id": classification_id,
                        "ok": True,
                        "already": True,
                        "review_status": "added_to_dataset",
                        "item": detail,
                    }
                )
                continue
            if previous != "approved":
                raise ReviewError(
                    "Only approved photos can be added to the dataset pool."
                )
            item = submit_review(
                actor,
                classification_id,
                action="added_to_dataset",
                confirm_change=True,
                notes="Added to unlabeled dataset pool (no class label assigned).",
            )
            results.append(
                {
                    "id": classification_id,
                    "ok": True,
                    "already": False,
                    "review_status": item.get("review_status"),
                    "item": item,
                }
            )
            succeeded.append(classification_id)
        except ReviewError as exc:
            entry = {"id": classification_id, "ok": False, "error": str(exc)}
            results.append(entry)
            failed.append({"id": classification_id, "error": str(exc)})
            current_app.logger.warning(
                "add_to_dataset_pool failed id=%s error=%s",
                classification_id,
                exc,
            )

    return {
        "ok": len(failed) == 0,
        "requested": len(ids),
        "succeeded_count": len(succeeded),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
        "results": results,
        "counts": contribution_counts(),
    }
