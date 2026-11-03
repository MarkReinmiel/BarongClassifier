"""One WSGI app for Render: Customer + Owner on a single Web Service (one bill).

Start (repo root, empty Root Directory):
  gunicorn -b 0.0.0.0:$PORT --workers 1 --timeout 120 --graceful-timeout 30 deploy.dual_host:application

Build (repo root):
  pip install -r requirements.txt

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


def _purge_app_modules() -> None:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]


def _stash_app_modules(prefix: str) -> None:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules[f"{prefix}.{name}"] = sys.modules.pop(name)


def _load_flask_app(project_root: Path, prefix: str):
    root = str(project_root.resolve())
    if not (project_root / "app" / "__init__.py").is_file():
        raise RuntimeError(f"Missing Flask package at {project_root / 'app'}")

    sys.path = [root] + [p for p in sys.path if Path(p).resolve() != Path(root).resolve()]
    _purge_app_modules()

    try:
        from dotenv import load_dotenv

        load_dotenv(project_root / ".env", override=False)
    except Exception:
        pass

    module = importlib.import_module("app")
    flask_app = module.create_app()
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
            return self.owner_app(environ, start_response)

        if host in self.owner_hosts or host.startswith("owner."):
            return self.owner_app(environ, start_response)

        if self.customer_hosts and host not in self.customer_hosts:
            # Unknown host still defaults to Customer
            pass
        return self.customer_app(environ, start_response)


def _build_application():
    logging.basicConfig(level=logging.INFO)
    logger.info("Loading Customer app from %s", CUSTOMER_ROOT)
    customer_app = _load_flask_app(CUSTOMER_ROOT, "_dual_customer")
    logger.info("Loading Owner app from %s", OWNER_ROOT)
    owner_app = _load_flask_app(OWNER_ROOT, "_dual_owner")

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
