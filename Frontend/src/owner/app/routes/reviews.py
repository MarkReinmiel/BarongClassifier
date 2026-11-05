"""Owner Customer Classification History + dataset review endpoints."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request

from app.services.review_service import ReviewError, list_approved_contributions
from app.services.review_service import (
    get_classification_detail,
    list_customer_classifications,
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
STATUS_OPTIONS = [
    ("", "All review statuses"),
    ("pending_review", "Pending Review"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
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


@bp.get("/customer-history")
@login_required
def customer_history():
    user = current_user()
    q = (request.args.get("q") or "").strip()
    fabric = (request.args.get("fabric") or "").strip()
    review_status = (request.args.get("status") or "").strip()
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
            review_status=review_status or None,
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
        status_options=STATUS_OPTIONS,
        date_options=DATE_OPTIONS,
        sort_options=SORT_OPTIONS,
        per_page_options=PER_PAGE_OPTIONS,
        q=q,
        selected_type=fabric,
        selected_status=review_status,
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
        # Owner identity comes only from the authenticated session (actor).
        # verified_label / rejection_reason are optional legacy fields and not required.
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
