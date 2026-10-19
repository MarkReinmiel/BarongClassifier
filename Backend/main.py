"""Authentication API. Classification stays on classify_server.py."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from auth.routes import router
from auth.service import AuthError
from auth.supabase_directory import build_service
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("barong.auth")

app = FastAPI(title="BarongClassifier Auth", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https?://(\[::1\]|localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)


@app.on_event("startup")
def check_configuration() -> None:
    missing = settings.missing_auth() + settings.missing_smtp()
    if missing:
        logger.error(
            "Authentication is not fully configured. Missing: %s",
            ", ".join(missing),
        )
    else:
        logger.info("Authentication configuration is present.")
    app.state.auth_service = None
    if not settings.supabase_url or not settings.supabase_anon_key:
        return
    try:
        app.state.auth_service = build_service()
    except Exception:
        logger.exception("Authentication client could not be created.")


@app.exception_handler(AuthError)
def auth_error(_request: Request, exc: AuthError) -> JSONResponse:
    body = {"error": str(exc)}
    if exc.retry_after_seconds:
        body["retry_after_seconds"] = exc.retry_after_seconds
    return JSONResponse(body, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
def validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    return JSONResponse({"error": "Check the information you entered."}, status_code=422)


@app.exception_handler(Exception)
def unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
    logger.exception("Request failed.")
    return JSONResponse({"error": "Something went wrong. Please try again."}, status_code=500)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
