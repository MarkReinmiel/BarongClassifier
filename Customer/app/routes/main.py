from flask import Blueprint, render_template

from app.services.statistics_service import dashboard_stats
from app.utils.security import current_user, nickname_required, no_store

bp = Blueprint("main", __name__)


@bp.after_request
def _private_headers(response):
    return no_store(response)


@bp.route("/")
def index():
    user = current_user()
    if user:
        if not user.nickname_completed:
            from flask import redirect, url_for

            return redirect(url_for("auth.nickname_setup"))
        from flask import redirect, url_for

        return redirect(url_for("main.dashboard"))
    from flask import redirect, url_for

    return redirect(url_for("auth.login"))


@bp.route("/dashboard")
@nickname_required
def dashboard():
    user = current_user()
    stats = dashboard_stats(user)
    return render_template("dashboard.html", user=user, stats=stats)


@bp.route("/textiletypes")
@nickname_required
def textile_types():
    user = current_user()
    return render_template("textiletypes.html", user=user)
