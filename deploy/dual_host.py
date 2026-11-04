"""One WSGI app for Render: Customer + Owner on a single Web Service (one bill).

Start (repo root, empty Root Directory):
  gunicorn -b 0.0.0.0:$PORT --workers 1 --timeout 120 --graceful-timeout 30 deploy.dual_host:application

Build (repo root):
  pip install -r requirements.txt
  # Includes numpy/tensorflow so Customer+Owner local CNN works on Render.

Access without a custom domain:
  Customer → https://YOUR-SERVICE.onrender.com/
  Owner    → https://YOUR-SERVICE.onrender.com/owner/

With custom domains (optional later):
  app.yourdomain.com     → Customer
  owner.yourdomain.com   → Owner

Env:
  CUSTOMER_BASE_URL=https://YOUR-SERVICE.onrender.com
  OWNER_BASE_URL=https://YOUR-SERVICE.onrender.com/owner
  CUSTOMER_HOSTS=YOUR-SERVICE.onrender.com
  OWNER_HOSTS=owner.yourdomain.com
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("deploy.dual_host")

REPO_ROOT = Path(__file__).resolve().parents[1]
CUSTOMER_ROOT = REPO_ROOT / "Frontend" / "src" / "customer"
OWNER_ROOT = REPO_ROOT / "Frontend" / "src" / "owner"
OWNER_PATH_PREFIX = (os.getenv("OWNER_PATH_PREFIX") or "/owner").rstrip("/") or "/owner"

CUSTOMER_PREFIX = "_dual_customer"
OWNER_PREFIX = "_dual_owner"


def _purge_live_app_modules() -> None:
    """Remove bare ``app`` / ``app.*`` keys only (keep stashed copies)."""
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]


def _stash_app_modules(prefix: str) -> None:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules[f"{prefix}.{name}"] = sys.modules.pop(name)


def _restore_app_modules(prefix: str) -> None:
    """Expose stashed ``{prefix}.app.*`` modules as live ``app.*`` for this request.

    Both portals ship a package named ``app``. Flask-SQLAlchemy resolves the
    engine from the extension bound during ``init_app``. Lazy imports and some
    FSA internals look up ``sys.modules['app']``, so the active portal's modules
    must be remounted on every request.
    """
    _purge_live_app_modules()
    prefix_app = f"{prefix}.app"
    for name, module in list(sys.modules.items()):
        if name == prefix_app or name.startswith(prefix_app + "."):
            live = name[len(prefix) + 1 :]  # "_dual_owner.app.models" -> "app.models"
            sys.modules[live] = module


def _prefer_project_path(project_root: Path) -> None:
    root = str(project_root.resolve())
    customer = str(CUSTOMER_ROOT.resolve())
    owner = str(OWNER_ROOT.resolve())
    others = [
        p
        for p in sys.path
        if Path(p).resolve().as_posix()
        not in {Path(root).resolve().as_posix(), Path(customer).resolve().as_posix(), Path(owner).resolve().as_posix()}
    ]
    sys.path = [root] + others


def _load_flask_app(project_root: Path, prefix: str):
    root = str(project_root.resolve())
    if not (project_root / "app" / "__init__.py").is_file():
        raise RuntimeError(f"Missing Flask package at {project_root / 'app'}")

    _prefer_project_path(project_root)
    _purge_live_app_modules()

    try:
        from dotenv import load_dotenv

        load_dotenv(project_root / ".env", override=False)
    except Exception:
        pass

    module = importlib.import_module("app")
    flask_app = module.create_app()

    # Keep a direct handle so request routing can remount the correct ``app`` package.
    flask_app.config["_DUAL_MODULE_PREFIX"] = prefix
    flask_app.config["_DUAL_PROJECT_ROOT"] = root

    with flask_app.app_context():
        # Fail fast at boot if SQLAlchemy did not bind to this app object.
        from app.extensions import db
        from sqlalchemy import text

        db.session.execute(text("select 1"))

    _stash_app_modules(prefix)
    return flask_app


def _host_list(env_name: str) -> set[str]:
    raw = os.getenv(env_name, "") or ""
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _request_host(environ: dict) -> str:
    forwarded = (environ.get("HTTP_X_FORWARDED_HOST") or "").split(",")[0].strip()
    host = forwarded or (environ.get("HTTP_HOST") or "")
    return host.split(":")[0].strip().lower()


class DualDispatcher:
    """Route by Owner path prefix, Owner hosts, else Customer."""

    def __init__(self, customer_app, owner_app, customer_hosts: set[str], owner_hosts: set[str]):
        self.customer_app = customer_app
        self.owner_app = owner_app
        self.customer_hosts = customer_hosts
        self.owner_hosts = owner_hosts
        self.owner_prefix = OWNER_PATH_PREFIX

    def _activate(self, flask_app) -> None:
        prefix = flask_app.config["_DUAL_MODULE_PREFIX"]
        root = Path(flask_app.config["_DUAL_PROJECT_ROOT"])
        _prefer_project_path(root)
        _restore_app_modules(prefix)
        self._ensure_sqlalchemy(flask_app, prefix)

    @staticmethod
    def _ensure_sqlalchemy(flask_app, prefix: str) -> None:
        """Make sure this Flask app is registered with its SQLAlchemy instance."""
        db = flask_app.extensions.get("sqlalchemy")
        if db is None:
            logger.error("No sqlalchemy extension on %s", prefix)
            return
        engines = getattr(db, "_app_engines", None)
        if isinstance(engines, dict) and flask_app in engines:
            return
        try:
            # Older/newer Flask-SQLAlchemy: probe via app context.
            with flask_app.app_context():
                _ = db.engine  # noqa: F841
            return
        except Exception:
            logger.warning("SQLAlchemy engine missing for %s — rebinding", prefix)
        try:
            db.init_app(flask_app)
            with flask_app.app_context():
                _ = db.engine  # noqa: F841
        except Exception:
            logger.exception("Failed to rebind SQLAlchemy for %s", prefix)

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO") or "/"
        host = _request_host(environ)

        # Same onrender URL: /owner → Owner app
        if path == self.owner_prefix or path.startswith(self.owner_prefix + "/"):
            environ = environ.copy()
            script = environ.get("SCRIPT_NAME") or ""
            environ["SCRIPT_NAME"] = script + self.owner_prefix
            rest = path[len(self.owner_prefix) :] or "/"
            if not rest.startswith("/"):
                rest = "/" + rest
            environ["PATH_INFO"] = rest
            self._activate(self.owner_app)
            return self.owner_app(environ, start_response)

        if host in self.owner_hosts or host.startswith("owner."):
            self._activate(self.owner_app)
            return self.owner_app(environ, start_response)

        if self.customer_hosts and host not in self.customer_hosts:
            # Unknown host still defaults to Customer
            pass
        self._activate(self.customer_app)
        return self.customer_app(environ, start_response)


def _build_application():
    logging.basicConfig(level=logging.INFO)
    logger.info("Loading Customer app from %s", CUSTOMER_ROOT)
    customer_app = _load_flask_app(CUSTOMER_ROOT, CUSTOMER_PREFIX)
    logger.info("Loading Owner app from %s", OWNER_ROOT)
    owner_app = _load_flask_app(OWNER_ROOT, OWNER_PREFIX)

    # Avoid Customer/Owner cookie clashes on the same hostname (/owner path).
    owner_app.config["SESSION_COOKIE_PATH"] = OWNER_PATH_PREFIX
    owner_app.config["SESSION_COOKIE_NAME"] = "owner_session"
    owner_app.config["REMEMBER_COOKIE_PATH"] = OWNER_PATH_PREFIX

    customer_base = os.getenv("CUSTOMER_BASE_URL") or os.getenv("BASE_URL") or ""
    owner_base = os.getenv("OWNER_BASE_URL") or os.getenv("OWNER_URL") or ""
    if customer_base:
        customer_app.config["BASE_URL"] = customer_base.rstrip("/")
    if owner_base:
        owner_app.config["BASE_URL"] = owner_base.rstrip("/")
        owner_app.config["OWNER_URL"] = owner_base.rstrip("/")
    elif customer_base:
        # Default Owner URL when only one onrender host exists
        owner_app.config["BASE_URL"] = customer_base.rstrip("/") + OWNER_PATH_PREFIX
        owner_app.config["OWNER_URL"] = owner_app.config["BASE_URL"]

    customer_hosts = _host_list("CUSTOMER_HOSTS")
    owner_hosts = _host_list("OWNER_HOSTS")
    logger.info(
        "Ready. Customer=/ Owner path=%s hosts customer=%s owner=%s",
        OWNER_PATH_PREFIX,
        customer_hosts or "(any)",
        owner_hosts or "(owner.*)",
    )
    return DualDispatcher(customer_app, owner_app, customer_hosts, owner_hosts)


application = _build_application()
