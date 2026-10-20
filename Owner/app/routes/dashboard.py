from __future__ import annotations

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.services.auth_service import AuthError, change_password
from app.services.users_service import (
    UsersError,
    dashboard_stats,
    list_directory_users,
    list_recent_classifications,
    update_user_role,
    update_user_status,
)
from app.utils.security import current_user, login_required, no_store

bp = Blueprint("dashboard", __name__)
FABRIC_OPTIONS = ["Piña", "Jusi", "Cocoon", "pina", "jusi", "cocoon"]


@bp.get("/dashboard")
@login_required
def home():
    user = current_user()
    stats = dashboard_stats()
    response = render_template("dashboard.html", user=user, stats=stats, active="dashboard")
    return no_store(response)


@bp.get("/about")
@login_required
def about():
    user = current_user()
    stats = dashboard_stats()
    response = render_template("about.html", user=user, stats=stats, active="about")
    return no_store(response)


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
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()
    fabric = (request.args.get("fabric") or "").strip()
    search_date = (request.args.get("search_date") or "").strip()
    if (request.args.get("today") or "") == "1":
        search_date = date.today().isoformat()
        date_from = ""
        date_to = ""

    rows = list_recent_classifications(
        date_from=date_from or None,
        date_to=date_to or None,
        fabric=fabric or None,
        search_date=search_date or None,
    )
    response = render_template(
        "history.html",
        user=user,
        rows=rows,
        active="history",
        fabric_options=FABRIC_OPTIONS,
        filters={
            "date_from": date_from,
            "date_to": date_to,
            "fabric": fabric,
            "search_date": search_date,
        },
    )
    return no_store(response)


@bp.get("/account")
@login_required
def account():
    user = current_user()
    response = render_template("account.html", user=user, active="account", error="")
    return no_store(response)


@bp.post("/account/change-password")
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
    response = render_template(
        "users.html",
        user=user,
        users=rows,
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


@bp.post("/users/<user_id>/status")
@login_required
def set_status(user_id: str):
    actor = current_user()
    active = (request.form.get("is_active") or "").lower() in {"1", "true", "yes", "on"}
    try:
        update_user_status(actor, user_id, active)
        flash("Status updated.", "success")
    except UsersError as exc:
        flash(str(exc), "error")
    return redirect(url_for("dashboard.users"))
