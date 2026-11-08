from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Config
from app.extensions import csrf, db, migrate

logger = logging.getLogger("owner.app")


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

    import app.models  # noqa: F401

    db.init_app(flask_app)
    migrate.init_app(
        flask_app,
        db,
        directory=str(Path(__file__).resolve().parents[1] / "migrations"),
    )
    csrf.init_app(flask_app)

    from app.routes.auth import bp as auth_bp
    from app.routes.classify import bp as classify_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.model_management import bp as model_management_bp
    from app.routes.password import bp as password_bp
    from app.routes.reviews import bp as reviews_bp

    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(password_bp)
    flask_app.register_blueprint(dashboard_bp)
    flask_app.register_blueprint(classify_bp)
    flask_app.register_blueprint(reviews_bp)
    flask_app.register_blueprint(model_management_bp)

    @flask_app.errorhandler(CSRFError)
    def csrf_error(error):
        wants_json = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in (request.headers.get("Accept") or "")
        )
        message = "Session expired. Refresh the page and try again."
        if wants_json:
            return jsonify({"ok": False, "error": message}), 400
        return render_template("errors/403.html"), 400

    @flask_app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @flask_app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @flask_app.errorhandler(500)
    def server_error(error):
        logger.exception("Internal server error: %s", error)
        return render_template("errors/500.html"), 500

    @flask_app.context_processor
    def inject_globals():
        from flask import url_for

        from app.services.turnstile_service import turnstile_active
        from app.utils.security import current_user

        try:
            user = current_user()
        except Exception:
            logger.exception("current_user() failed in template context")
            user = None
        try:
            active = turnstile_active()
        except Exception:
            active = False
        return {
            "app_name": flask_app.config["APP_NAME"],
            "current_user": user,
            "turnstile_enabled": active,
            "turnstile_site_key": (flask_app.config.get("TURNSTILE_SITE_KEY") or "") if active else "",
            "user_avatar_url": url_for("static", filename="images/avatar-unknown.svg") + "?v=1",
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
