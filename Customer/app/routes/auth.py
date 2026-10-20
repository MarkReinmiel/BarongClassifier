from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import generate_csrf

from app.extensions import csrf, db
from app.models import CustomerUser, utcnow
from app.services import auth_service
from app.services.auth_service import AuthError
from app.utils.security import client_label, current_user, login_required, mask_email, no_store

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _json_error(error: AuthError):
    body = {"error": str(error)}
    if error.retry_after is not None:
        body["retry_after_seconds"] = error.retry_after
    return jsonify(body), error.status_code


@bp.after_request
def _private_headers(response):
    return no_store(response)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("main.dashboard"))

    if request.method == "GET":
        return render_template("auth/register.html")

    email = request.form.get("email", "")
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    wants_json = request.accept_mimetypes.best == "application/json" or request.is_json

    try:
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            email = payload.get("email", "")
            password = payload.get("password", "")
            confirm = payload.get("confirm_password", password)
        user = auth_service.register_user(email, password, confirm)
    except AuthError as error:
        if wants_json or request.is_json:
            return _json_error(error)
        flash(str(error), "error")
        return render_template("auth/register.html", email=email), error.status_code

    session.clear()
    session["pending_user_id"] = str(user.id)
    session["pending_purpose"] = "registration"
    session.modified = True
    if wants_json or request.is_json:
        return jsonify(
            {
                "verification_required": True,
                "email_hint": mask_email(user.email),
                "redirect": url_for("auth.verify_email"),
            }
        )
    return redirect(url_for("auth.verify_email"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        user = current_user()
        if user and not user.nickname_completed:
            return redirect(url_for("auth.nickname_setup"))
        return redirect(url_for("main.dashboard"))

    if request.method == "GET":
        return render_template("auth/login.html")

    email = request.form.get("email", "")
    password = request.form.get("password", "")
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        email = payload.get("email", email)
        password = payload.get("password", password)

    try:
        user = auth_service.authenticate(email, password)
    except AuthError as error:
        if error.status_code == 403 and "Verify your email" in str(error):
            found = CustomerUser.query.filter_by(email=email.strip().lower()).first()
            if found:
                session["pending_user_id"] = str(found.id)
                session["pending_purpose"] = "registration"
                try:
                    auth_service.issue_and_send_code(found, "registration")
                except AuthError:
                    pass
            flash(str(error), "error")
            return redirect(url_for("auth.verify_email"))
        flash(str(error), "error")
        return render_template("auth/login.html"), error.status_code

    cookie_name = current_app.config["DEVICE_COOKIE_NAME"]
    raw_device = request.cookies.get(cookie_name)
    if auth_service.device_is_trusted(user, raw_device):
        return _complete_login(user)

    try:
        auth_service.issue_and_send_code(user, "device")
    except AuthError as error:
        flash(str(error), "error")
        return render_template("auth/login.html"), error.status_code

    session.clear()
    session["pending_user_id"] = str(user.id)
    session["pending_purpose"] = "device"
    session["pending_login"] = True
    session.modified = True
    return redirect(url_for("auth.verify_device"))


def _complete_login(user: CustomerUser, set_device: bool = False):
    session.clear()
    session["user_id"] = str(user.id)
    session.permanent = True
    session.modified = True
    user.last_login_at = utcnow()
    db.session.commit()

    target = url_for("auth.nickname_setup") if not user.nickname_completed else url_for("main.dashboard")
    response = make_response(redirect(target))
    if set_device:
        token = auth_service.trust_device(user, client_label())
        response.set_cookie(
            current_app.config["DEVICE_COOKIE_NAME"],
            token,
            httponly=True,
            samesite="Lax",
            secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")),
            max_age=current_app.config["DEVICE_TRUST_DAYS"] * 86400,
        )
    return response


@bp.route("/verify-email", methods=["GET"])
def verify_email():
    user = _pending_user("registration")
    if not user:
        flash("Sign up or sign in again to verify your email.", "error")
        return redirect(url_for("auth.register"))
    wait = auth_service.resend_wait_seconds(user, "registration")
    return render_template(
        "auth/verify_email.html",
        email_hint=mask_email(user.email),
        resend_after_seconds=wait,
        purpose="registration",
    )


@bp.route("/verify-device", methods=["GET"])
def verify_device():
    user = _pending_user("device")
    if not user:
        flash("Sign in again to verify this browser.", "error")
        return redirect(url_for("auth.login"))
    wait = auth_service.resend_wait_seconds(user, "device")
    return render_template(
        "auth/verify_device.html",
        email_hint=mask_email(user.email),
        resend_after_seconds=wait,
        purpose="device",
    )


@bp.route("/verification-status", methods=["GET"])
def verification_status():
    purpose = request.args.get("purpose") or session.get("pending_purpose") or "registration"
    user = _pending_user(purpose)
    if not user:
        return jsonify({"error": "Verification session expired."}), 401
    wait = auth_service.resend_wait_seconds(user, purpose)
    return jsonify(
        {
            "resend_after_seconds": wait,
            "expires_in_seconds": current_app.config["EMAIL_VERIFICATION_EXPIRE_MINUTES"] * 60,
            "email_hint": mask_email(user.email),
        }
    )


@bp.route("/verify-code", methods=["POST"])
def verify_code():
    payload = request.get_json(silent=True) or {}
    purpose = payload.get("purpose") or session.get("pending_purpose") or "registration"
    code = payload.get("code") or request.form.get("code", "")
    user = _pending_user(purpose)
    if not user:
        return jsonify({"error": "Verification session expired."}), 401
    try:
        auth_service.verify_code(user, purpose, code)
    except AuthError as error:
        return _json_error(error)

    if purpose == "device":
        token = auth_service.trust_device(user, client_label())
        session.clear()
        session["user_id"] = str(user.id)
        session.permanent = True
        session.modified = True
        user.last_login_at = utcnow()
        db.session.commit()
        target = (
            url_for("auth.nickname_setup")
            if not user.nickname_completed
            else url_for("main.dashboard")
        )
        response = make_response(
            jsonify({"verified": True, "redirect": target})
        )
        response.set_cookie(
            current_app.config["DEVICE_COOKIE_NAME"],
            token,
            httponly=True,
            samesite="Lax",
            secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")),
            max_age=current_app.config["DEVICE_TRUST_DAYS"] * 86400,
        )
        return response

    session.pop("pending_user_id", None)
    session.pop("pending_purpose", None)
    return jsonify(
        {
            "verified": True,
            "message": "Email verified successfully.",
            "login_url": url_for("auth.login"),
        }
    )


@bp.route("/resend-code", methods=["POST"])
def resend_code():
    payload = request.get_json(silent=True) or {}
    purpose = payload.get("purpose") or session.get("pending_purpose") or "registration"
    user = _pending_user(purpose)
    if not user:
        return jsonify({"error": "Verification session expired."}), 401
    try:
        result = auth_service.issue_and_send_code(user, purpose)
    except AuthError as error:
        return _json_error(error)
    return jsonify(
        {
            "message": "A new code was sent.",
            "resend_after_seconds": result["resend_after_seconds"],
            "resend_available_at": result["resend_available_at"],
        }
    )


@bp.route("/nickname", methods=["GET", "POST"])
@login_required
def nickname_setup():
    user = current_user()
    assert user is not None
    if user.nickname_completed:
        return redirect(url_for("main.dashboard"))

    if request.method == "GET":
        return render_template("auth/nickname.html", user=user)

    nickname = request.form.get("nickname", "")
    if request.is_json:
        nickname = (request.get_json(silent=True) or {}).get("nickname", nickname)
    try:
        auth_service.save_nickname(user, nickname)
    except AuthError as error:
        if request.is_json:
            return _json_error(error)
        flash(str(error), "error")
        return render_template("auth/nickname.html", user=user), 400
    if request.is_json:
        return jsonify({"ok": True, "redirect": url_for("main.dashboard")})
    return redirect(url_for("main.dashboard"))


@bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    response = make_response(redirect(url_for("auth.login")))
    response.delete_cookie(current_app.config["DEVICE_COOKIE_NAME"])
    return response


@bp.route("/csrf-token", methods=["GET"])
def csrf_token():
    return jsonify({"csrf_token": generate_csrf()})


def _pending_user(purpose: str) -> CustomerUser | None:
    user_id = session.get("pending_user_id")
    if not user_id:
        return None
    if session.get("pending_purpose") not in {None, purpose}:
        # Allow explicit purpose override when matching pending purpose.
        if session.get("pending_purpose") != purpose:
            return None
    return CustomerUser.query.filter_by(id=user_id, is_active=True).first()
