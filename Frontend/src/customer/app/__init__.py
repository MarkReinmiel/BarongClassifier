from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Config
from app.extensions import csrf, db, migrate

logger = logging.getLogger("customer.app")


def create_app(config_object: type[Config] = Config) -> Flask:
    flask_app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="templates",
        static_folder="static",
    )
    flask_app.config.from_object(config_object)
    Path(flask_app.instance_path).mkdir(parents=True, exist_ok=True)

    if not flask_app.config.get("TESTING") and not flask_app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError(
            "Database is not configured. Set DATABASE_URL or DB_HOST/DB_USERNAME/DB_PASSWORD."
        )

    # Import models before init so metadata is complete for Alembic.
    import app.models  # noqa: F401

    db.init_app(flask_app)
    migrate.init_app(
        flask_app,
        db,
        directory=str(Path(__file__).resolve().parents[1] / "migrations"),
    )
    csrf.init_app(flask_app)

    from app.routes.auth import bp as auth_bp
    from app.routes.classifier import bp as classifier_bp
    from app.routes.history import bp as history_bp
    from app.routes.main import bp as main_bp
    from app.routes.password import bp as password_bp

    flask_app.register_blueprint(main_bp)
    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(password_bp)
    flask_app.register_blueprint(classifier_bp)
    flask_app.register_blueprint(history_bp)

    @flask_app.errorhandler(CSRFError)
    def csrf_error(_error):
        flash("Your session expired. Please try again.", "error")
        target = request.referrer or url_for("auth.login")
        # Prefer auth pages when the token fails on login/register.
        path = (request.path or "").lower()
        if path.startswith("/auth/login"):
            target = url_for("auth.login")
        elif path.startswith("/auth/register"):
            target = url_for("auth.register")
        elif path.startswith("/auth/forgot-password"):
            target = url_for("password.forgot_password")
        elif path.startswith("/auth/reset-password"):
            target = url_for("password.reset_password")
        return redirect(target)

    @flask_app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @flask_app.errorhandler(413)
    def too_large(_error):
        return render_template("errors/413.html"), 413

    @flask_app.errorhandler(500)
    def server_error(_error):
        try:
            db.session.rollback()
        except Exception:
            pass
        return render_template("errors/500.html"), 500

    @flask_app.context_processor
    def inject_globals():
        from flask import url_for

        from app.utils.security import current_user

        from app.services.turnstile_service import turnstile_active

        try:
            user = current_user()
        except Exception:
            logger.exception("current_user() failed in template context")
            user = None
        try:
            active = turnstile_active()
        except Exception:
            active = False
        import json as _json

        tour_progress = {
            "main": True,
            "classify": True,
            "textile": True,
            "history": True,
            "profile": True,
        }
        if user and getattr(user, "nickname_completed", False):
            try:
                from app.services.tour_service import get_tour_progress

                tour_progress = get_tour_progress(user)
            except Exception:
                logger.exception("tour progress failed in template context")
                try:
                    db.session.rollback()
                except Exception:
                    pass
        # Pre-serialize so templates never call |tojson on Undefined/odd types.
        tour_progress_json = _json.dumps(tour_progress)
        return {
            "app_name": flask_app.config["APP_NAME"],
            "current_user": user,
            "user_avatar_url": url_for("static", filename="images/avatar-unknown.svg") + "?v=10",
            "turnstile_enabled": active,
            "turnstile_site_key": (flask_app.config.get("TURNSTILE_SITE_KEY") or "") if active else "",
            "tour_progress": tour_progress,
            "tour_progress_json": tour_progress_json,
        }

    @flask_app.get("/health")
    def health():
        db_ok = False
        try:
            db.session.execute(text("select 1"))
            db_ok = True
        except SQLAlchemyError:
            logger.exception("Health check could not reach the database.")
            db.session.rollback()
        status = 200 if db_ok else 503
        return jsonify({"ok": db_ok, "database": "up" if db_ok else "down"}), status

    return flask_app
