from flask import Blueprint, render_template, request

from app.services.history_service import list_for_user
from app.utils.security import current_user, nickname_required, no_store

bp = Blueprint("history", __name__)


@bp.after_request
def _private_headers(response):
    return no_store(response)


@bp.route("/history")
@nickname_required
def history_page():
    user = current_user()
    page = request.args.get("page", 1)
    result = list_for_user(
        user,
        fabric=request.args.get("type"),
        page=page,
        per_page=50,
    )
    return render_template(
        "history.html",
        user=user,
        rows=result["items"],
        selected_type=(request.args.get("type") or "").strip(),
        page=result["page"],
        pages=result["pages"],
        total=result["total"],
    )
