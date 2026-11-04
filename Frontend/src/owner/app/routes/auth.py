from __future__ import annotations

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.services.auth_service import AuthError, authenticate_owner, touch_login
from app.services.turnstile_service import TurnstileError, turnstile_active, verify_turnstile
from app.utils.security import current_user, is_owner_role, mask_email, no_store
from app.models import OwnerUser

bp = Blueprint("auth", __name__)


def _safe_next(value: str | None) -> str | None:
    if not value or not value.startswith("/") or value.startswith("//"):
        return None
    return value


def _redirect_within_app(path: str | None):
    """Redirect under this app's SCRIPT_NAME (e.g. /owner).

    ``redirect('/dashboard')`` would leave /owner and hit the Customer app.
    """
    if not path:
        return redirect(url_for("dashboard.home"))
    root = request.script_root or ""
    if root and (path == root or path.startswith(root + "/")):
        return redirect(path)
    if path.startswith("/"):
        return redirect(f"{root}{path}")
    return redirect(url_for("dashboard.home"))


@bp.get("/")
def home():
    user = current_user()
    if user and is_owner_role(user.role):
        return redirect(url_for("dashboard.home"))
    return render_template("landing.html")


@bp.get("/login")
@bp.post("/login")
def login():
    if current_user() and is_owner_role(current_user().role):
        return redirect(url_for("dashboard.home"))

    error = ""
    email_value = ""
    if request.method == "POST":
        email_value = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))
        nxt = _safe_next(request.args.get("next") or request.form.get("next"))
        try:
            user = authenticate_owner(email_value, password)
            if turnstile_active():
                session.clear()
                session["pending_owner_id"] = str(user.id)
                session["pending_purpose"] = "human"
                session["pending_remember"] = remember
                session["pending_next"] = nxt or ""
                session.modified = True
                return redirect(url_for("auth.verify_human"))
            return _complete_owner_login(user, remember=remember, nxt=nxt)
        except AuthError as exc:
            error = str(exc)
        except Exception:
            from flask import current_app

            current_app.logger.exception("Owner login failed unexpectedly.")
            try:
                from app.extensions import db

                db.session.rollback()
            except Exception:
                pass
            error = "Sign in could not be completed. Please try again."

    response = render_template(
        "auth/login.html",
        error=error,
        email_value=email_value,
        next_url=_safe_next(request.args.get("next")) or "",
    )
    return no_store(response)


def _complete_owner_login(user: OwnerUser, remember: bool = False, nxt: str | None = None):
    session.clear()
    session["owner_user_id"] = str(user.id)
    session["owner_role"] = user.role
    session.permanent = bool(remember)
    session.modified = True
    touch_login(user)
    return _redirect_within_app(nxt)


def _pending_owner() -> OwnerUser | None:
    if session.get("pending_purpose") != "human":
        return None
    user_id = session.get("pending_owner_id")
    if not user_id:
        return None
    try:
        return OwnerUser.query.filter_by(id=str(user_id), is_active=True).first()
    except Exception:
        return None


@bp.get("/verify-human")
@bp.post("/verify-human")
def verify_human():
    user = _pending_owner()
    if not user or not is_owner_role(user.role):
        flash("Sign in again to complete human verification.", "error")
        return redirect(url_for("auth.login"))

    remember = bool(session.get("pending_remember"))
    nxt = _safe_next(session.get("pending_next"))

    if not turnstile_active():
        return _complete_owner_login(user, remember=remember, nxt=nxt)

    error = ""
    if request.method == "POST":
        try:
            verify_turnstile(request.form.get("cf-turnstile-response"))
            return _complete_owner_login(user, remember=remember, nxt=nxt)
        except TurnstileError as exc:
            error = str(exc)

    response = render_template(
        "auth/verify_human.html",
        email_hint=mask_email(user.email),
        error=error,
    )
    return no_store(response)


@bp.post("/logout")
def logout():
    session.clear()
    flash("You have signed out.", "success")
    return redirect(url_for("auth.login"))
