"""One WSGI app for Render: route Customer vs Owner by Host (subdomain).

Usage (Render start command, repo root as service root):
  gunicorn -b 0.0.0.0:$PORT deploy.dual_host:application

Custom domains on the SAME Web Service:
  app.yourdomain.com    -> Customer
  owner.yourdomain.com  -> Owner

Env (optional, comma-separated hosts):
  CUSTOMER_HOSTS=app.yourdomain.com,barongcognition.onrender.com
  OWNER_HOSTS=owner.yourdomain.com
  CUSTOMER_BASE_URL=https://app.yourdomain.com
  OWNER_BASE_URL=https://owner.yourdomain.com
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


def _purge_app_modules() -> None:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]


def _stash_app_modules(prefix: str) -> None:
    """Rename imported app.* modules so the other side can import app again."""
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            stashed = f"{prefix}.{name}"
            sys.modules[stashed] = sys.modules.pop(name)


def _load_flask_app(project_root: Path, prefix: str):
    root = str(project_root.resolve())
    if not (project_root / "app" / "__init__.py").is_file():
        raise RuntimeError(f"Missing Flask package at {project_root / 'app'}")

    # Prefer this project on sys.path
    sys.path = [root] + [p for p in sys.path if Path(p).resolve() != Path(root).resolve()]
    _purge_app_modules()

    # Ensure .env from this project is available for local runs (Render uses dashboard env).
    try:
        from dotenv import load_dotenv

        load_dotenv(project_root / ".env", override=False)
    except Exception:
        pass

    module = importlib.import_module("app")
    flask_app = module.create_app()
    _stash_app_modules(prefix)
    return flask_app


def _host_list(env_name: str, fallback: str = "") -> set[str]:
    raw = os.getenv(env_name, fallback) or ""
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _request_host(environ: dict) -> str:
    forwarded = (environ.get("HTTP_X_FORWARDED_HOST") or "").split(",")[0].strip()
    host = forwarded or (environ.get("HTTP_HOST") or "")
    return host.split(":")[0].strip().lower()


class HostDispatcher:
    def __init__(self, customer_app, owner_app, customer_hosts: set[str], owner_hosts: set[str]):
        self.customer_app = customer_app
        self.owner_app = owner_app
        self.customer_hosts = customer_hosts
        self.owner_hosts = owner_hosts

    def __call__(self, environ, start_response):
        host = _request_host(environ)
        if host in self.owner_hosts or host.startswith("owner."):
            return self.owner_app(environ, start_response)
        if host in self.customer_hosts:
            return self.customer_app(environ, start_response)
        # Default: Customer (main site / onrender.com)
        return self.customer_app(environ, start_response)


def _build_application():
    logging.basicConfig(level=logging.INFO)
    logger.info("Loading Customer app from %s", CUSTOMER_ROOT)
    customer_app = _load_flask_app(CUSTOMER_ROOT, "_dual_customer")
    logger.info("Loading Owner app from %s", OWNER_ROOT)
    owner_app = _load_flask_app(OWNER_ROOT, "_dual_owner")

    customer_base = os.getenv("CUSTOMER_BASE_URL") or os.getenv("BASE_URL") or ""
    owner_base = os.getenv("OWNER_BASE_URL") or os.getenv("OWNER_URL") or ""
    if customer_base:
        customer_app.config["BASE_URL"] = customer_base
    if owner_base:
        owner_app.config["BASE_URL"] = owner_base
        owner_app.config["OWNER_URL"] = owner_base

    customer_hosts = _host_list("CUSTOMER_HOSTS")
    owner_hosts = _host_list("OWNER_HOSTS")
    logger.info("Customer hosts=%s Owner hosts=%s", customer_hosts or "(default)", owner_hosts or "(owner.*)")

    return HostDispatcher(customer_app, owner_app, customer_hosts, owner_hosts)


application = _build_application()
