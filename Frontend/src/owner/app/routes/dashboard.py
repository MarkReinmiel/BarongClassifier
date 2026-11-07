from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.services.auth_service import AuthError, change_password, update_owner_profile
from app.services.model_analytics_service import analytics_json
from app.services.users_service import (
    UsersError,
    dashboard_stats,
    delete_classification,
    delete_user,
    list_directory_users,
    list_recent_classifications,
    update_user_role,
    update_user_status,
    update_user_verified,
)
from app.utils.security import current_user, login_required, no_store

bp = Blueprint("dashboard", __name__)
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


@bp.get("/dashboard")
@login_required
def home():
    user = current_user()
    stats = dashboard_stats()
    recent = list_recent_classifications(limit=5)["items"]
    response = render_template(
        "dashboard.html",
        user=user,
        stats=stats,
        recent=recent,
        active="dashboard",
    )
    return no_store(response)


@bp.get("/about")
@login_required
def about():
    user = current_user()
    stats = dashboard_stats()
    response = render_template("about.html", user=user, stats=stats, active="about")
    return no_store(response)


@bp.get("/model-analytics")
@login_required
def model_analytics():
    user = current_user()
    measure = (request.args.get("measure_latency") or "").lower() in {"1", "true", "yes"}
    data = analytics_json(measure_latency=measure)
    response = render_template(
        "model_analytics.html",
        user=user,
        analytics=data,
        active="analytics",
    )
    return no_store(response)


@bp.get("/api/model-analytics")
@login_required
def model_analytics_api():
    measure = (request.args.get("measure_latency") or "").lower() in {"1", "true", "yes"}
    return jsonify(analytics_json(measure_latency=measure))


@bp.get("/textile-types")
@login_required
def textile_types():
    user = current_user()
    response = render_template("textile_types.html", user=user, active="textiletypes")
    return no_store(response)


@bp.get("/history")
@login_required
def history():
    user = current_user()
    fabric = (request.args.get("fabric") or request.args.get("type") or "").strip()
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

    result = list_recent_classifications(
        page=page,
        per_page=per_page,
        date_preset=date_preset or None,
        fabric=fabric or None,
    )
    response = render_template(
        "history.html",
        user=user,
        rows=result["items"],
        active="history",
        fabric_options=FABRIC_OPTIONS,
        date_options=DATE_OPTIONS,
        per_page_options=PER_PAGE_OPTIONS,
        selected_type=fabric,
        date_preset=date_preset,
        page=result["page"],
        pages=result["pages"],
        total=result["total"],
        per_page=result["per_page"],
    )
    return no_store(response)


@bp.post("/history/<classification_id>/delete")
@login_required
def delete_history_item(classification_id: str):
    wants_json = (
        "application/json" in (request.accept_mimetypes.best or "")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )
    try:
        delete_classification(classification_id)
    except UsersError as error:
        if wants_json:
            return jsonify({"ok": False, "error": str(error)}), int(
                getattr(error, "status_code", 400) or 400
            )
        flash(str(error), "error")
        return redirect(url_for("dashboard.history"))
    if wants_json:
        return jsonify({"ok": True})
    flash("Classification deleted.", "success")
    return redirect(
        url_for(
            "dashboard.history",
            fabric=request.args.get("fabric") or request.form.get("fabric") or "",
            date=request.args.get("date") or request.form.get("date") or "",
            per_page=request.args.get("per_page") or request.form.get("per_page") or 10,
            page=request.args.get("page") or request.form.get("page") or 1,
        )
    )


@bp.get("/account")
@login_required
def account():
    user = current_user()
    response = render_template("account.html", user=user, active="account", error="")
    return no_store(response)


@bp.post("/account/profile", endpoint="update_profile")
@login_required
def update_profile_view():
    user = current_user()
    error = ""
    try:
        update_owner_profile(
            user,
            request.form.get("full_name") or "",
            request.form.get("phone") or "",
        )
        flash("Profile updated.", "success")
        return redirect(url_for("dashboard.account"))
    except AuthError as exc:
        error = str(exc)
    response = render_template("account.html", user=user, active="account", error=error)
    return no_store(response)


@bp.post("/account/change-password", endpoint="change_password")
@login_required
def change_password_view():
    user = current_user()
    error = ""
    try:
        change_password(
            user,
            request.form.get("current_password") or "",
            request.form.get("new_password") or "",
            request.form.get("confirm_password") or "",
        )
        flash("Password updated.", "success")
        return redirect(url_for("dashboard.account"))
    except AuthError as exc:
        error = str(exc)
    response = render_template("account.html", user=user, active="account", error=error)
    return no_store(response)


@bp.get("/users")
@login_required
def users():
    user = current_user()
    rows = list_directory_users()
    active_count = sum(1 for row in rows if row.get("is_active"))
    response = render_template(
        "users.html",
        user=user,
        users=rows,
        users_total=len(rows),
        users_active=active_count,
        users_inactive=max(0, len(rows) - active_count),
        active="users",
    )
    return no_store(response)


@bp.post("/users/<user_id>/role")
@login_required
def set_role(user_id: str):
    actor = current_user()
    role = request.form.get("role") or ""
    try:
        update_user_role(actor, user_id, role)
        flash("Role updated.", "success")
    except UsersError as exc:
        flash(str(exc), "error")
    return redirect(url_for("dashboard.users"))


def _wants_json() -> bool:
    if request.args.get("format") == "json":
        return True
    if request.accept_mimetypes.best == "application/json":
        return True
    if (request.headers.get("X-Requested-With") or "").lower() == "xmlhttprequest":
        return True
    payload = request.get_json(silent=True)
    return isinstance(payload, dict)


def _parse_bool(value, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@bp.post("/users/<user_id>/status")
@login_required
def set_status(user_id: str):
    actor = current_user()
    payload = request.get_json(silent=True) or {}
    raw = payload.get("is_active", request.form.get("is_active"))
    active = _parse_bool(raw, default=False)
    try:
        result = update_user_status(actor, user_id, active)
    except UsersError as exc:
        if _wants_json():
            return jsonify({"ok": False, "error": str(exc)}), int(getattr(exc, "status_code", 400) or 400)
        flash(str(exc), "error")
        return redirect(url_for("dashboard.users"))

    if _wants_json():
        return jsonify({"ok": True, "user": result})
    flash("Status updated.", "success")
    return redirect(url_for("dashboard.users"))


@bp.post("/users/<user_id>/verified")
@login_required
def set_verified(user_id: str):
    actor = current_user()
    payload = request.get_json(silent=True) or {}
    raw = payload.get("email_verified", request.form.get("email_verified"))
    verified = _parse_bool(raw, default=False)
    try:
        result = update_user_verified(actor, user_id, verified)
    except UsersError as exc:
        if _wants_json():
            return jsonify({"ok": False, "error": str(exc)}), int(getattr(exc, "status_code", 400) or 400)
        flash(str(exc), "error")
        return redirect(url_for("dashboard.users"))

    if _wants_json():
        return jsonify({"ok": True, "user": result})
    flash("Verification updated.", "success")
    return redirect(url_for("dashboard.users"))


@bp.post("/users/<user_id>/delete")
@login_required
def remove_user(user_id: str):
    actor = current_user()
    try:
        delete_user(actor, user_id)
        flash("User deleted.", "success")
    except UsersError as exc:
        flash(str(exc), "error")
    return redirect(url_for("dashboard.users"))
