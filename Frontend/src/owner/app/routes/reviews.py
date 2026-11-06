"""Owner Customer Classification History + dataset review endpoints."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request

from app.services.review_service import ReviewError, list_approved_contributions
from app.services.review_service import (
    add_to_dataset_pool,
    remove_from_dataset_pool,
    get_classification_detail,
    list_customer_classifications,
    submit_batch_review,
    submit_review,
)
from app.utils.security import current_user, login_required, no_store

bp = Blueprint("reviews", __name__)

FABRIC_OPTIONS = [
    ("", "All textile types"),
    ("pina", "Piña"),
    ("jusi", "Jusi"),
    ("cocoon", "Cocoon"),
    ("undefined_textile", "Undefined Textile"),
]
DATE_OPTIONS = [
    ("", "All dates"),
    ("today", "Today"),
    ("7d", "Last 7 days"),
    ("30d", "Last 30 days"),
]
SORT_OPTIONS = [
    ("newest", "Newest first"),
    ("oldest", "Oldest first"),
]
PER_PAGE_OPTIONS = [12, 24, 48]
PANELS = frozenset({"pending", "approved", "rejected"})


@bp.get("/customer-history")
@login_required
def customer_history():
    user = current_user()
    q = (request.args.get("q") or "").strip()
    fabric = (request.args.get("fabric") or "").strip()
    panel = (request.args.get("panel") or "pending").strip().lower()
    if panel not in PANELS:
        panel = "pending"
    date_preset = (request.args.get("date") or "").strip()
    date_from = (request.args.get("date_from") or "").strip() or None
    date_to = (request.args.get("date_to") or "").strip() or None
    sort = (request.args.get("sort") or "newest").strip().lower()
    if sort not in {"newest", "oldest"}:
        sort = "newest"
    try:
        page = int(request.args.get("page") or 1)
    except ValueError:
        page = 1
    try:
        per_page = int(request.args.get("per_page") or 12)
    except ValueError:
        per_page = 12
    if per_page not in PER_PAGE_OPTIONS:
        per_page = 12

    error = ""
    try:
        result = list_customer_classifications(
            page=page,
            per_page=per_page,
            q=q or None,
            fabric=fabric or None,
            panel=panel,
            date_preset=date_preset or None,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
        )
    except ReviewError as exc:
        error = str(exc)
        result = {
            "items": [],
            "total": 0,
            "page": 1,
            "pages": 1,
            "per_page": per_page,
            "counts": {},
        }

    response = render_template(
        "customer_history.html",
        user=user,
        rows=result["items"],
        counts=result.get("counts") or {},
        active="customer_history",
        fabric_options=FABRIC_OPTIONS,
        date_options=DATE_OPTIONS,
        sort_options=SORT_OPTIONS,
        per_page_options=PER_PAGE_OPTIONS,
        q=q,
        selected_type=fabric,
        panel=panel,
        date_preset=date_preset,
        date_from=date_from or "",
        date_to=date_to or "",
        sort=sort,
        page=result["page"],
        pages=result["pages"],
        total=result["total"],
        per_page=result["per_page"],
        error=error,
    )
    return no_store(response)


@bp.get("/dataset-contributions")
@login_required
def dataset_contributions():
    user = current_user()
    verified = (request.args.get("label") or "").strip()
    try:
        page = int(request.args.get("page") or 1)
    except ValueError:
        page = 1
    error = ""
    try:
        result = list_approved_contributions(
            page=page,
            per_page=24,
            verified_label=verified or None,
        )
    except ReviewError as exc:
        error = str(exc)
        result = {
            "items": [],
            "total": 0,
            "page": 1,
            "pages": 1,
            "per_page": 24,
            "counts": {},
        }

    response = render_template(
        "dataset_contributions.html",
        user=user,
        rows=result["items"],
        counts=result.get("counts") or {},
        active="contributions",
        selected_label=verified,
        page=result["page"],
        pages=result["pages"],
        total=result["total"],
        per_page=result["per_page"],
        error=error,
    )
    return no_store(response)


@bp.post("/api/classifications/review/batch")
@login_required
def classification_review_batch_api():
    actor = current_user()
    assert actor is not None
    payload = request.get_json(silent=True) or {}
    action = (payload.get("action") or "").strip().lower()
    ids = payload.get("ids") or payload.get("classification_ids") or []
    if not isinstance(ids, list):
        return jsonify({"ok": False, "error": "ids must be a list."}), 400
    try:
        result = submit_batch_review(actor, ids, action=action)
        current_app.logger.info(
            "batch_review action=%s actor=%s requested=%s succeeded=%s failed=%s",
            action,
            actor.id,
            result.get("requested"),
            result.get("succeeded_count"),
            result.get("failed_count"),
        )
        status = 200 if result.get("ok") or result.get("succeeded_count") else 400
        return jsonify(result), status
    except ReviewError as exc:
        current_app.logger.warning(
            "batch_review failed action=%s actor=%s error=%s",
            action,
            getattr(actor, "id", None),
            exc,
        )
        return jsonify({"ok": False, "error": str(exc)}), exc.status_code


@bp.post("/api/classifications/dataset/batch")
@login_required
def classification_dataset_batch_api():
    actor = current_user()
    assert actor is not None
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids") or payload.get("classification_ids") or []
    action = (payload.get("action") or "add").strip().lower()
    if not isinstance(ids, list):
        return jsonify({"ok": False, "error": "ids must be a list."}), 400
    try:
        if action in {"remove", "remove_from_dataset", "undo"}:
            result = remove_from_dataset_pool(actor, ids)
            log_label = "dataset_remove"
        else:
            result = add_to_dataset_pool(actor, ids)
            log_label = "dataset_batch"
        current_app.logger.info(
            "%s actor=%s requested=%s succeeded=%s skipped=%s failed=%s",
            log_label,
            actor.id,
            result.get("requested"),
            result.get("succeeded_count"),
            result.get("skipped_count"),
            result.get("failed_count"),
        )
        status = 200 if result.get("ok") or result.get("succeeded_count") or result.get(
            "skipped_count"
        ) else 400
        return jsonify(result), status
    except ReviewError as exc:
        current_app.logger.warning(
            "dataset_batch failed actor=%s action=%s error=%s",
            getattr(actor, "id", None),
            action,
            exc,
        )
        return jsonify({"ok": False, "error": str(exc)}), exc.status_code


@bp.get("/api/classifications/<classification_id>")
@login_required
def classification_detail_api(classification_id: str):
    try:
        detail = get_classification_detail(classification_id)
        return jsonify({"ok": True, "item": detail})
    except ReviewError as exc:
        return jsonify({"ok": False, "error": str(exc)}), exc.status_code


@bp.post("/api/classifications/<classification_id>/review")
@login_required
def classification_review_api(classification_id: str):
    actor = current_user()
    assert actor is not None
    payload = request.get_json(silent=True) or {}
    if not payload:
        payload = request.form.to_dict()
    action = (payload.get("action") or "").strip().lower()
    try:
        confirm_raw = payload.get("confirm_change")
        confirm_change = str(confirm_raw).lower() in {"1", "true", "yes", "on"}
        detail = submit_review(
            actor,
            classification_id,
            action=action,
            verified_label=payload.get("verified_label"),
            rejection_reason=payload.get("rejection_reason"),
            notes=payload.get("notes"),
            confirm_change=confirm_change,
        )
        current_app.logger.info(
            "classification_review ok action=%s classification_id=%s actor=%s status=%s",
            action,
            classification_id,
            actor.id,
            detail.get("review_status"),
        )
        return jsonify({"ok": True, "item": detail})
    except ReviewError as exc:
        current_app.logger.warning(
            "classification_review failed action=%s classification_id=%s actor=%s error=%s",
            action,
            classification_id,
            getattr(actor, "id", None),
            exc,
        )
        return jsonify({"ok": False, "error": str(exc)}), exc.status_code
