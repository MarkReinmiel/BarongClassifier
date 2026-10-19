"""Auth and admin HTTP routes. The frontend role is never trusted."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, EmailStr, Field

from auth.permissions import RateLimiter
from auth.service import AuthError, AuthService

router = APIRouter()
limiter = RateLimiter()


class RegisterBody(BaseModel):
    full_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class CodeBody(BaseModel):
    verification_token: str = Field(min_length=10, max_length=500)
    code: str = Field(min_length=6, max_length=6)


class ResendBody(BaseModel):
    verification_token: str = Field(min_length=10, max_length=500)


class PasswordBody(BaseModel):
    new_password: str = Field(min_length=8, max_length=200)


class RoleBody(BaseModel):
    role: str


class StatusBody(BaseModel):
    is_active: bool


def get_service(request: Request) -> AuthService:
    service = getattr(request.app.state, "auth_service", None)
    if service is None:
        raise AuthError("The authentication service is not configured.", 503)
    return service


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def guard(request: Request) -> None:
    if not limiter.allow(client_key(request)):
        raise AuthError("Too many requests. Wait a moment and try again.", 429)


def bearer(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Sign in again.", 401)
    return authorization.split(" ", 1)[1].strip()


@router.post("/api/auth/register")
def register(body: RegisterBody, request: Request, service: AuthService = Depends(get_service)):
    guard(request)
    return service.register(body.full_name, str(body.email), body.password)


@router.post("/api/auth/login")
def login(body: LoginBody, request: Request, service: AuthService = Depends(get_service)):
    guard(request)
    return service.login(str(body.email), body.password)


@router.get("/api/auth/verification-status")
def verification_status(
    verification_token: str,
    request: Request,
    service: AuthService = Depends(get_service),
):
    guard(request)
    return service.verification_status(verification_token)


@router.post("/api/auth/verify-code")
def verify_code(body: CodeBody, request: Request, service: AuthService = Depends(get_service)):
    guard(request)
    return service.verify(body.verification_token, body.code)


@router.post("/api/auth/resend-code")
def resend_code(body: ResendBody, request: Request, service: AuthService = Depends(get_service)):
    guard(request)
    return service.resend(body.verification_token)


@router.post("/api/auth/send-verification")
def send_verification(body: ResendBody, request: Request, service: AuthService = Depends(get_service)):
    guard(request)
    return service.resend(body.verification_token)


@router.post("/api/auth/logout")
def logout():
    return {"message": "Signed out."}


@router.get("/api/auth/me")
def me(token: str = Depends(bearer), service: AuthService = Depends(get_service)):
    profile = service.current_user(token)
    return {
        "id": profile.id,
        "email": profile.email,
        "full_name": profile.full_name,
        "role": profile.role,
        "must_change_password": profile.must_change_password,
    }


@router.post("/api/auth/change-password")
def change_password(
    body: PasswordBody,
    token: str = Depends(bearer),
    service: AuthService = Depends(get_service),
):
    service.change_password(token, body.new_password)
    return {"message": "Password updated."}


@router.get("/api/admin/users")
def admin_users(token: str = Depends(bearer), service: AuthService = Depends(get_service)):
    return {"users": service.list_users(token)}


@router.patch("/api/admin/users/{user_id}/role")
def admin_role(
    user_id: str,
    body: RoleBody,
    token: str = Depends(bearer),
    service: AuthService = Depends(get_service),
):
    service.update_role(token, user_id, body.role)
    return {"message": "Role updated."}


@router.patch("/api/admin/users/{user_id}/status")
def admin_status(
    user_id: str,
    body: StatusBody,
    token: str = Depends(bearer),
    service: AuthService = Depends(get_service),
):
    service.update_status(token, user_id, body.is_active)
    return {"message": "Status updated."}
