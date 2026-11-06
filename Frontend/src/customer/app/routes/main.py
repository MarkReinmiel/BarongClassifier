from flask import Blueprint, jsonify, render_template, request

from app.services.statistics_service import dashboard_stats
from app.services.tour_service import (
    get_tour_progress,
    mark_section_completed,
    section_needs_tour,
    should_launch_tour,
)
from app.utils.security import current_user, nickname_required, no_store

bp = Blueprint("main", __name__)


@bp.after_request
def _private_headers(response):
    return no_store(response)


@bp.route("/")
def index():
    from flask import redirect, url_for

    user = current_user()
    if user:
        if not user.nickname_completed:
            return redirect(url_for("auth.nickname_setup"))
        return redirect(url_for("main.dashboard"))
    return render_template("landing.html")


@bp.route("/dashboard")
@nickname_required
def dashboard():
    user = current_user()
    try:
        stats = dashboard_stats(user)
    except Exception:
        stats = {
            "textile_types": 3,
            "model_accuracy": "—",
            "images_classified": 0,
            "recent": [],
        }
    try:
        launch = should_launch_tour(user)
        progress = get_tour_progress(user)
    except Exception:
        launch = False
        progress = {"main": True, "textile": True, "history": True, "profile": True}
    return render_template(
        "dashboard.html",
        user=user,
        stats=stats,
        launch_tour=launch,
        tour_progress=progress,
    )


@bp.route("/tour/complete", methods=["POST"])
@nickname_required
def tour_complete():
    """Mark one tour section done (main | textile | history | profile)."""
    user = current_user()
    assert user is not None
    payload = request.get_json(silent=True) or {}
    section = (payload.get("section") or request.form.get("section") or "main").strip()
    try:
        progress = mark_section_completed(user, section)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "progress": progress})
    from flask import redirect, url_for

    return redirect(url_for("main.dashboard"))


@bp.route("/tour/progress", methods=["GET"])
@nickname_required
def tour_progress():
    user = current_user()
    return jsonify({"ok": True, "progress": get_tour_progress(user)})


@bp.route("/textiletypes")
@nickname_required
def textile_types():
    user = current_user()
    return render_template(
        "textiletypes.html",
        user=user,
        launch_textile_tour=section_needs_tour(user, "textile"),
        tour_progress=get_tour_progress(user),
    )
