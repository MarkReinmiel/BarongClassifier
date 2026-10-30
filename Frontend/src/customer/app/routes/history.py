from flask import Blueprint, render_template, request

from app.services.history_service import list_for_user
from app.utils.security import current_user, nickname_required, no_store

bp = Blueprint("history", __name__)
FABRIC_OPTIONS = [
    ("", "All fabric types"),
    ("pina", "Piña"),
    ("jusi", "Jusi"),
    ("cocoon", "Cocoon"),
]
DATE_OPTIONS = [
    ("", "All dates"),
    ("today", "Today"),
    ("7d", "Last 7 days"),
    ("30d", "Last 30 days"),
]
PER_PAGE_OPTIONS = [10, 25, 50]


@bp.after_request
def _private_headers(response):
    return no_store(response)


@bp.route("/history")
@nickname_required
def history_page():
    user = current_user()
    selected_type = (request.args.get("type") or "").strip()
    date_preset = (request.args.get("date") or "").strip()
    try:
        page = int(request.args.get("page") or 1)
    except ValueError:
        page = 1
    try:
        per_page = int(request.args.get("per_page") or 10)
    except ValueError:
        per_page = 10
    if per_page not in PER_PAGE_OPTIONS:
        per_page = 10

    result = list_for_user(
        user,
        fabric=selected_type or None,
        date_preset=date_preset or None,
        page=page,
        per_page=per_page,
    )
    return render_template(
        "history.html",
        user=user,
        rows=result["items"],
        selected_type=selected_type,
        date_preset=date_preset,
        page=result["page"],
        pages=result["pages"],
        total=result["total"],
        per_page=result["per_page"],
        fabric_options=FABRIC_OPTIONS,
        date_options=DATE_OPTIONS,
        per_page_options=PER_PAGE_OPTIONS,
    )
