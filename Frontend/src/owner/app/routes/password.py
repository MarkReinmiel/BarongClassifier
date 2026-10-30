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

from app.models import OwnerUser
from app.services.auth_service import (
    PURPOSE_RESET,
    AuthError,
    issue_and_send_code,
    request_password_reset,
    resend_wait_seconds,
    reset_password as apply_password_reset,
    verify_code,
)
from app.services.turnstile_service import TurnstileError, verify_turnstile
from app.utils.security import mask_email, no_store

bp = Blueprint("password", __name__)


def _reset_user() -> OwnerUser | None:
    user_id = session.get("reset_user_id")
    if not user_id:
        return None
    return OwnerUser.query.filter_by(id=user_id, is_active=True).first()


@bp.get("/forgot-password")
@bp.post("/forgot-password")
def forgot_password():
    error = ""
    email_value = ""
    if request.method == "POST":
        email_value = (request.form.get("email") or "").strip()
        try:
            verify_turnstile(request.form.get("cf-turnstile-response"))
            user = request_password_reset(email_value)
            session["reset_user_id"] = user.id
            session.pop("reset_authorized", None)
            flash("A verification code was sent to your email.", "success")
            return redirect(url_for("password.verify_reset_code"))
        except (AuthError, TurnstileError) as exc:
            error = str(exc)

    response = render_template(
        "auth/forgot_password.html",
        error=error,
        email_value=email_value,
    )
    return no_store(response)


@bp.get("/verify-reset-code")
@bp.post("/verify-reset-code")
def verify_reset_code():
    user = _reset_user()
    if not user:
        flash("Start password recovery with your email first.", "error")
        return redirect(url_for("password.forgot_password"))

    error = ""
    if request.method == "POST":
        action = (request.form.get("action") or "verify").strip()
        try:
            if action == "resend":
                issue_and_send_code(user, PURPOSE_RESET)
                flash("A new code was sent to your email.", "success")
            else:
                digits = "".join(
                    (request.form.get(f"d{i}") or "").strip() for i in range(1, 7)
                )
                if not digits:
                    digits = (request.form.get("code") or "").strip()
                verify_code(user, PURPOSE_RESET, digits)
                session["reset_authorized"] = True
                flash("Code verified. Choose a new password.", "success")
                return redirect(url_for("password.reset_password"))
        except AuthError as exc:
            error = str(exc)

    response = render_template(
        "auth/verify_email.html",
        error=error,
        masked_email=mask_email(user.email),
        resend_wait=resend_wait_seconds(user, PURPOSE_RESET),
    )
    return no_store(response)


@bp.get("/reset-password")
@bp.post("/reset-password")
def reset_password():
    user = _reset_user()
    if not user or not session.get("reset_authorized"):
        flash("Verify the email code before resetting your password.", "error")
        return redirect(url_for("password.forgot_password"))

    error = ""
    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        try:
            apply_password_reset(user, password, confirm)
            session.pop("reset_user_id", None)
            session.pop("reset_authorized", None)
            session.clear()
            flash("Password updated. Sign in with your new password.", "success")
            return redirect(url_for("auth.login"))
        except AuthError as exc:
            error = str(exc)
            if exc.status_code == 502:
                session.pop("reset_user_id", None)
                session.pop("reset_authorized", None)
                flash(str(exc), "error")
                return redirect(url_for("auth.login"))

    response = render_template("auth/reset_password.html", error=error)
    return no_store(response)
