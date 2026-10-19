"""Auth rules without SMTP, Supabase, or production data."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from config import settings

settings.email_verification_enabled = True

from auth.permissions import can_view_history
from auth.routes import router
from auth.service import AuthError, AuthService, UserRecord
from auth.verification import utcnow
from fastapi.responses import JSONResponse
from services.email_service import EmailDeliveryError


class FakeDirectory:
    def __init__(self) -> None:
        self.users: dict[str, UserRecord] = {}
        self.passwords: dict[str, str] = {}
        self.revoked = 0
        self.sessions: list[str] = []

    def add(self, profile: UserRecord, password: str) -> None:
        self.users[profile.id] = profile
        self.passwords[profile.email] = password

    def create_customer(self, email: str, password: str, full_name: str):
        if email in self.passwords:
            return None
        profile = UserRecord(email, email, full_name, "customer", True, False, False)
        profile.id = email
        self.add(profile, password)
        return profile

    def authenticate(self, email: str, password: str):
        profile = next((item for item in self.users.values() if item.email == email), None)
        if not profile or self.passwords.get(email) != password:
            return None
        return {
            "profile": profile,
            "session": {"access_token": profile.id, "refresh_token": "refresh", "expires_in": 3600, "token_type": "bearer"},
            "access_token": profile.id,
        }

    def revoke(self, signed_in: dict) -> None:
        self.revoked += 1

    def get_profile(self, user_id: str) -> UserRecord:
        return self.users[user_id]

    def mark_login(self, user_id: str) -> None:
        return None

    def mark_verified(self, user_id: str) -> None:
        self.users[user_id].email_verified = True

    def create_session(self, email: str) -> dict:
        self.sessions.append(email)
        return {"access_token": email, "refresh_token": "refresh", "expires_in": 3600, "token_type": "bearer"}

    def profile_from_token(self, access_token: str):
        return self.users.get(access_token)

    def change_password(self, access_token: str, user_id: str, new_password: str) -> None:
        self.passwords[self.users[user_id].email] = new_password
        self.users[user_id].must_change_password = False

    def list_profiles(self, actor_id: str):
        return [{"id": item.id, "role": item.role} for item in self.users.values()]

    def set_role(self, user_id: str, role: str) -> None:
        self.users[user_id].role = role

    def set_active(self, user_id: str, is_active: bool) -> None:
        self.users[user_id].is_active = is_active


def profile(user_id, role="customer", active=True, verified=True, password_change=False):
    return UserRecord(
        id=user_id,
        email=f"{user_id}@example.com",
        full_name=user_id,
        role=role,
        is_active=active,
        email_verified=verified,
        must_change_password=password_change,
    )


def service_for(directory, mailer):
    from auth.verification import MemoryVerificationStore

    return AuthService(
        MemoryVerificationStore(),
        directory,
        mailer=mailer,
        require_config=False,
    )


def recording_mailer():
    sent = []

    def mailer(recipient, code):
        sent.append((recipient, code))

    mailer.sent = sent
    return mailer


def test_wrong_and_correct_login():
    directory = FakeDirectory()
    person = profile("ada", verified=True)
    directory.add(person, "correct-password")
    mailer = recording_mailer()
    service = service_for(directory, mailer)
    try:
        service.login(person.email, "nope")
        raised = False
    except AuthError as error:
        raised = error.status_code == 401
    assert raised
    result = service.login(person.email, "correct-password")
    assert result["session"]["access_token"] == person.id
    assert result["verification_required"] is False


def test_verification_success_failure_expiry_and_reuse():
    directory = FakeDirectory()
    person = profile("bea", verified=False)
    directory.add(person, "correct-password")
    mailer = recording_mailer()
    service = service_for(directory, mailer)
    started = service.login(person.email, "correct-password")
    assert "session" not in started
    assert directory.revoked == 1
    token = started["verification_token"]
    code = mailer.sent[-1][1]

    try:
        service.verify(token, "000000")
        assert False
    except AuthError as error:
        assert error.status_code == 400

    verified = service.verify(token, code)
    assert verified["session"]["access_token"] == person.email
    assert directory.users[person.id].email_verified is True

    try:
        service.verify(token, code)
        assert False
    except AuthError:
        pass

    person.email_verified = False
    started = service.login(person.email, "correct-password")
    fresh = mailer.sent[-1][1]
    row = service.store.codes[person.id][-1]
    row.expires_at = utcnow() - timedelta(seconds=1)
    try:
        service.verify(started["verification_token"], fresh)
        assert False
    except AuthError as error:
        assert "expired" in str(error).lower()


def test_resend_cooldown_and_attempt_lock():
    directory = FakeDirectory()
    person = profile("cy", verified=False)
    directory.add(person, "correct-password")
    mailer = recording_mailer()
    service = service_for(directory, mailer)
    started = service.login(person.email, "correct-password")
    try:
        service.resend(started["verification_token"])
        assert False
    except AuthError as error:
        assert error.status_code == 429

    for _ in range(5):
        try:
            service.verify(started["verification_token"], "111111")
        except AuthError:
            pass
    try:
        service.verify(started["verification_token"], mailer.sent[-1][1])
        assert False
    except AuthError as error:
        assert error.status_code == 429


def test_smtp_failure_does_not_report_success():
    directory = FakeDirectory()
    person = profile("dee", verified=False)
    directory.add(person, "correct-password")

    def mailer(_recipient, _code):
        raise EmailDeliveryError("down")

    service = service_for(directory, mailer)
    try:
        service.login(person.email, "correct-password")
        assert False
    except AuthError as error:
        assert error.status_code == 502


def test_registration_is_customer_and_customers_cannot_escalate():
    directory = FakeDirectory()
    mailer = recording_mailer()
    service = service_for(directory, mailer)
    service.register("New Person", "new@example.com", "long-password")
    assert directory.users["new@example.com"].role == "customer"
    directory.users["new@example.com"].email_verified = True
    try:
        service.update_role("new@example.com", "ada", "admin")
        assert False
    except AuthError as error:
        assert error.status_code == 403


def test_admin_owner_and_customer_access():
    directory = FakeDirectory()
    admin = profile("admin", role="admin")
    owner = profile("owner", role="owner")
    customer = profile("guest", role="customer")
    directory.add(admin, "pw")
    directory.add(owner, "pw")
    directory.add(customer, "pw")
    service = service_for(directory, recording_mailer())
    assert len(service.list_users(admin.id)["users"] if False else service.list_users(admin.id)) == 3
    for actor in (owner.id, customer.id):
        try:
            service.list_users(actor)
            assert False
        except AuthError as error:
            assert error.status_code == 403


def test_inactive_login_is_rejected():
    directory = FakeDirectory()
    person = profile("inactive", active=False)
    directory.add(person, "correct-password")
    service = service_for(directory, recording_mailer())
    try:
        service.login(person.email, "correct-password")
        assert False
    except AuthError as error:
        assert error.status_code == 403
    assert directory.revoked == 1


def test_history_ownership_and_protected_routes():
    assert can_view_history("guest", "customer", "guest")
    assert not can_view_history("guest", "customer", "owner")
    assert not can_view_history("owner", "owner", "guest")
    assert can_view_history("admin", "admin", "guest")

    directory = FakeDirectory()
    service = service_for(directory, recording_mailer())
    app = FastAPI()
    app.state.auth_service = service
    app.include_router(router)

    @app.exception_handler(AuthError)
    def _auth_error(_request, exc: AuthError):
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code)

    client = TestClient(app)
    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    denied = client.get("/api/auth/me")
    assert denied.status_code == 401
    admin_denied = client.get("/api/admin/users")
    assert admin_denied.status_code == 401


def test_classification_alias_migration_keeps_existing_columns():
    sql = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20261020000200_create_classification_history.sql"
    ).read_text(encoding="utf-8")
    assert "predicted_label" in sql
    assert "image_path" in sql
    assert "classifications_sync_aliases" in sql
    server = (BACKEND / "machine learning" / "classify_server.py").read_text(encoding="utf-8")
    assert "/predict" in server
