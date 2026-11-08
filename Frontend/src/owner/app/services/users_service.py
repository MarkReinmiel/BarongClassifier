"""Owner directory views over public.users / customer.users (shared DB)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import OwnerUser, utcnow
from app.utils.validators import normalize_email

ASSIGNABLE = frozenset({"owner", "customer"})
INACTIVITY_DAYS = 5


class UsersError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _nickname_value(*values: str | None) -> str:
    for value in values:
        text_value = (value or "").strip()
        if text_value:
            return text_value
    return ""


def _last_activity_at(*values: datetime | None) -> datetime | None:
    stamped = [_as_utc(value) for value in values if value is not None]
    if not stamped:
        return None
    return max(stamped)


def _is_inactive_by_activity(last_activity: datetime | None, *, now: datetime | None = None) -> bool:
    """True when last activity is missing or at least INACTIVITY_DAYS old."""
    if last_activity is None:
        return True
    current = _as_utc(now) or datetime.now(timezone.utc)
    return current - _as_utc(last_activity) >= timedelta(days=INACTIVITY_DAYS)


def evaluate_user_flags(
    *,
    nickname: str | None,
    last_activity: datetime | None,
    stored_active: bool | None = None,
    stored_verified: bool | None = None,
) -> dict:
    """Derive active/verified from activity + nickname only (no manual flags).

    - Active: last activity newer than INACTIVITY_DAYS
    - Verified: nickname is present (non-empty)
    stored_* args are ignored; kept for call-site compatibility.
    """
    del stored_active, stored_verified
    has_nickname = bool(_nickname_value(nickname))
    inactive = _is_inactive_by_activity(last_activity)
    return {
        "is_active": not inactive,
        "email_verified": has_nickname,
        "has_nickname": has_nickname,
        "inactive_by_inactivity": inactive,
    }


def dashboard_stats() -> dict:
    """Frontend-style overview numbers plus directory counts."""
    stats = {
        "textile_types": 3,
        "model_accuracy": None,
        "test_images": None,
        "users_total": 0,
        "owners_total": 0,
        "customers_total": 0,
        "classifications_total": 0,
        "active_users": 0,
    }
    try:
        from app.services.model_analytics_service import load_active_metrics

        metrics = load_active_metrics()
        if metrics.get("test_accuracy") is not None:
            stats["model_accuracy"] = round(float(metrics["test_accuracy"]) * 100)
        if metrics.get("test_images") is not None:
            stats["test_images"] = int(metrics["test_images"])
    except Exception:
        pass
    if current_app.config.get("TESTING"):
        rows = OwnerUser.query.all()
        stats["users_total"] = len(rows)
        stats["owners_total"] = sum(1 for r in rows if (r.role or "").lower() == "owner")
        stats["customers_total"] = sum(1 for r in rows if (r.role or "").lower() == "customer")
        stats["active_users"] = sum(1 for r in rows if r.is_active)
        return stats

    try:
        row = db.session.execute(
            text(
                """
                select
                  count(*)::int as users_total,
                  count(*) filter (where role::text = 'owner')::int as owners_total,
                  count(*) filter (where role::text = 'customer')::int as customers_total,
                  count(*) filter (where coalesce(is_active, true))::int as active_users
                from public.users
                """
            )
        ).mappings().first()
        if row:
            stats.update(dict(row))
    except SQLAlchemyError:
        db.session.rollback()
        rows = OwnerUser.query.all()
        stats["users_total"] = len(rows)
        stats["owners_total"] = sum(1 for r in rows if (r.role or "").lower() == "owner")
        stats["customers_total"] = sum(1 for r in rows if (r.role or "").lower() == "customer")
        stats["active_users"] = sum(1 for r in rows if r.is_active)

    try:
        count = db.session.execute(
            text("select count(*)::int as n from public.classifications")
        ).scalar()
        stats["classifications_total"] = int(count or 0)
    except SQLAlchemyError:
        db.session.rollback()

    return stats


def _serialize_directory_user(row: dict) -> dict:
    nickname = _nickname_value(row.get("nickname"), row.get("customer_nickname"))
    # Active/inactive is driven by real login/sign-in only — not updated_at
    # (admin/system writes). Never-logged-in accounts fall back to created_at.
    last_activity = _last_activity_at(
        row.get("last_login_at"),
        row.get("customer_last_login_at"),
        row.get("last_sign_in_at"),
        row.get("auth_last_sign_in_at"),
    ) or _last_activity_at(
        row.get("public_created_at"),
        row.get("customer_created_at"),
        row.get("created_at"),
    )
    flags = evaluate_user_flags(nickname=nickname, last_activity=last_activity)
    full_name = (row.get("full_name") or "").strip() or nickname
    return {
        "id": str(row.get("id")),
        "email": row.get("email") or "",
        "full_name": full_name,
        "nickname": nickname,
        "role": row.get("role") or "customer",
        "status": "active" if flags["is_active"] else "inactive",
        "is_active": flags["is_active"],
        "email_verified": flags["email_verified"],
        "has_nickname": flags["has_nickname"],
        "source": row.get("source") or "",
        "last_activity_at": last_activity.isoformat() if last_activity else None,
    }


def list_directory_users() -> list[dict]:
    if current_app.config.get("TESTING"):
        serialized = []
        for u in OwnerUser.query.order_by(OwnerUser.created_at.desc()).all():
            serialized.append(
                _serialize_directory_user(
                    {
                        "id": str(u.id),
                        "email": u.email,
                        "full_name": u.full_name or "",
                        "nickname": u.nickname or "",
                        "role": u.role,
                        "status": u.status,
                        "is_active": bool(u.is_active),
                        "email_verified": bool(u.email_verified),
                        "source": "customer",
                        "last_login_at": u.last_login_at,
                        "updated_at": u.updated_at,
                        "created_at": u.created_at,
                    }
                )
            )
        return serialized

    try:
        rows = db.session.execute(
            text(
                """
                select
                  p.id::text as id,
                  p.email,
                  coalesce(p.full_name, '') as full_name,
                  coalesce(p.nickname, '') as nickname,
                  coalesce(c.nickname, '') as customer_nickname,
                  p.role::text as role,
                  p.status,
                  coalesce(p.is_active, true) as is_active,
                  coalesce(p.email_verified, false) as email_verified,
                  coalesce(p.source, '') as source,
                  p.last_login_at as last_login_at,
                  p.last_sign_in_at as last_sign_in_at,
                  c.last_login_at as customer_last_login_at,
                  a.last_sign_in_at as auth_last_sign_in_at,
                  p.created_at as public_created_at,
                  c.created_at as customer_created_at,
                  coalesce(c.created_at, p.created_at) as created_at
                from public.users p
                left join customer.users c
                  on c.id = p.id::text
                  or lower(trim(c.email)) = lower(trim(p.email))
                left join auth.users a
                  on a.id = p.id
                order by p.created_at desc nulls last
                limit 200
                """
            )
        ).mappings().all()
        return [_serialize_directory_user(dict(r)) for r in rows]
    except SQLAlchemyError:
        db.session.rollback()
        return [
            _serialize_directory_user(
                {
                    "id": str(u.id),
                    "email": u.email,
                    "full_name": u.full_name or "",
                    "nickname": u.nickname or "",
                    "role": u.role,
                    "status": u.status,
                    "is_active": bool(u.is_active),
                    "email_verified": bool(u.email_verified),
                    "source": "customer",
                    "last_login_at": u.last_login_at,
                    "updated_at": u.updated_at,
                    "created_at": u.created_at,
                }
            )
            for u in OwnerUser.query.order_by(OwnerUser.created_at.desc()).limit(200).all()
        ]


def _enable_trusted_user_write() -> None:
    """Allow role/is_active changes past public.protect_user_privileges()."""
    db.session.execute(text("select set_config('app.trusted_profile_write', '1', true)"))


def _directory_role(user_id: str) -> str | None:
    row = db.session.execute(
        text("select role::text as role from public.users where id::text = :id limit 1"),
        {"id": str(user_id)},
    ).mappings().first()
    return (row["role"] if row else None)


def _find_customer_user(user_id: str) -> OwnerUser | None:
    target = OwnerUser.query.filter_by(id=str(user_id)).first()
    if target:
        return target
    email = db.session.execute(
        text("select lower(trim(email)) from public.users where id::text = :id limit 1"),
        {"id": str(user_id)},
    ).scalar()
    if email:
        return OwnerUser.query.filter_by(email=normalize_email(email)).first()
    return None


def _apply_public_role(user_id: str, role: str) -> None:
    result = db.session.execute(
        text(
            """
            update public.users
            set role = cast(:role as public.app_role),
                updated_at = now()
            where id::text = :id
              and role::text <> 'admin'
            """
        ),
        {"role": role, "id": str(user_id)},
    )
    if result.rowcount == 0:
        raise UsersError("User role could not be updated.", 404)
    verify = db.session.execute(
        text("select role::text as role from public.users where id::text = :id"),
        {"id": str(user_id)},
    ).mappings().first()
    if not verify or (verify["role"] or "").lower() != role:
        raise UsersError("User role was blocked by database privileges.", 503)


def _apply_public_status(user_id: str, active: bool, status_value: str, email: str | None = None) -> None:
    """Update directory row by id and/or email (ids can diverge across tables)."""
    _enable_trusted_user_write()
    normalized_email = normalize_email(email or "") if email else ""
    result = db.session.execute(
        text(
            """
            update public.users
            set is_active = cast(:active as boolean),
                status = :status,
                updated_at = now()
            where role::text <> 'admin'
              and (
                id::text = :id
                or (:email <> '' and lower(trim(email)) = :email)
              )
            """
        ),
        {
            "active": active,
            "status": status_value,
            "id": str(user_id),
            "email": normalized_email,
        },
    )
    if result.rowcount == 0:
        raise UsersError("User status could not be updated.", 404)
    verify = db.session.execute(
        text(
            """
            select coalesce(is_active, true) as is_active
            from public.users
            where id::text = :id
               or (:email <> '' and lower(trim(email)) = :email)
            order by case when id::text = :id then 0 else 1 end
            limit 1
            """
        ),
        {"id": str(user_id), "email": normalized_email},
    ).mappings().first()
    if not verify or bool(verify["is_active"]) != bool(active):
        raise UsersError("User status was blocked by database privileges.", 503)


def _apply_public_verified(user_id: str, verified: bool, email: str | None = None) -> None:
    _enable_trusted_user_write()
    normalized_email = normalize_email(email or "") if email else ""
    result = db.session.execute(
        text(
            """
            update public.users
            set email_verified = cast(:verified as boolean),
                updated_at = now()
            where role::text <> 'admin'
              and (
                id::text = :id
                or (:email <> '' and lower(trim(email)) = :email)
              )
            """
        ),
        {
            "verified": verified,
            "id": str(user_id),
            "email": normalized_email,
        },
    )
    if result.rowcount == 0:
        raise UsersError("Email verification could not be updated.", 404)
    verify = db.session.execute(
        text(
            """
            select coalesce(email_verified, false) as email_verified
            from public.users
            where id::text = :id
               or (:email <> '' and lower(trim(email)) = :email)
            order by case when id::text = :id then 0 else 1 end
            limit 1
            """
        ),
        {"id": str(user_id), "email": normalized_email},
    ).mappings().first()
    if not verify or bool(verify["email_verified"]) != bool(verified):
        raise UsersError("Email verification was blocked by database privileges.", 503)


def update_user_role(actor: OwnerUser, user_id: str, role: str) -> None:
    role = (role or "").strip().lower()
    if role not in ASSIGNABLE:
        raise UsersError("Role must be owner or customer.")
    if str(actor.id) == str(user_id):
        raise UsersError("You cannot change your own role here.", 403)

    if current_app.config.get("TESTING"):
        target = OwnerUser.query.filter_by(id=user_id).first()
        if not target:
            raise UsersError("User was not found.", 404)
        if (target.role or "").lower() == "admin":
            raise UsersError("Admin accounts cannot be changed here.", 403)
        target.role = role
        target.updated_at = utcnow()
        db.session.commit()
        return

    try:
        _enable_trusted_user_write()
        directory_role = _directory_role(user_id)
        target = _find_customer_user(user_id)

        if directory_role is None and target is None:
            raise UsersError("User was not found.", 404)
        if (directory_role or (target.role if target else "") or "").lower() == "admin":
            raise UsersError("Admin accounts cannot be changed here.", 403)

        # Mirror portal row first (sync trigger also needs the trusted flag).
        if target is not None:
            target.role = role
            target.updated_at = utcnow()
            db.session.flush()

        # Directory page reads public.users — write/verify it last.
        if directory_role is not None:
            _apply_public_role(user_id, role)

        db.session.commit()
    except UsersError:
        db.session.rollback()
        raise
    except SQLAlchemyError as error:
        db.session.rollback()
        raise UsersError("User role could not be updated.", 503) from error


def update_user_status(actor: OwnerUser, user_id: str, is_active: bool) -> dict:
    if str(actor.id) == str(user_id) and not is_active:
        raise UsersError("You cannot deactivate your own Owner session here.", 403)

    active = bool(is_active)
    status_value = "active" if active else "disabled"

    if current_app.config.get("TESTING"):
        target = OwnerUser.query.filter_by(id=user_id).first()
        if not target:
            raise UsersError("User was not found.", 404)
        if (target.role or "").lower() == "admin":
            raise UsersError("Admin accounts cannot be changed here.", 403)
        target.is_active = active
        target.status = status_value
        if active:
            target.last_login_at = utcnow()
        target.updated_at = utcnow()
        db.session.commit()
        flags = evaluate_user_flags(
            nickname=target.nickname,
            last_activity=target.last_login_at or target.updated_at or target.created_at,
        )
        return {
            "id": str(target.id),
            "is_active": flags["is_active"],
            "status": "active" if flags["is_active"] else "inactive",
            "email_verified": flags["email_verified"],
            "has_nickname": flags["has_nickname"],
        }

    try:
        _enable_trusted_user_write()
        directory_role = _directory_role(user_id)
        target = _find_customer_user(user_id)

        if directory_role is None and target is None:
            raise UsersError("User was not found.", 404)
        if (directory_role or (target.role if target else "") or "").lower() == "admin":
            raise UsersError("Admin accounts cannot be changed here.", 403)

        email = (target.email if target else None) or db.session.execute(
            text("select lower(trim(email)) from public.users where id::text = :id limit 1"),
            {"id": str(user_id)},
        ).scalar()

        if target is not None:
            target.is_active = active
            target.status = status_value
            if active:
                target.last_login_at = utcnow()
            target.updated_at = utcnow()
            db.session.flush()

        try:
            _apply_public_status(user_id, active, status_value, email=email)
            if active:
                _enable_trusted_user_write()
                db.session.execute(
                    text(
                        """
                        update public.users
                        set last_login_at = now(),
                            updated_at = now()
                        where role::text <> 'admin'
                          and (
                            id::text = :id
                            or (:email <> '' and lower(trim(email)) = :email)
                          )
                        """
                    ),
                    {
                        "id": str(user_id),
                        "email": normalize_email(email or "") if email else "",
                    },
                )
        except UsersError:
            # Portal-only accounts may have no public.users directory row.
            if directory_role is not None or target is None:
                raise
        db.session.commit()

        nickname = _nickname_value(getattr(target, "nickname", None))
        flags = evaluate_user_flags(
            nickname=nickname,
            last_activity=utcnow() if active else getattr(target, "last_login_at", None),
        )
        return {
            "id": str(user_id),
            "is_active": flags["is_active"],
            "status": "active" if flags["is_active"] else "inactive",
            "email_verified": flags["email_verified"],
            "has_nickname": flags["has_nickname"],
        }
    except UsersError:
        db.session.rollback()
        raise
    except SQLAlchemyError as error:
        db.session.rollback()
        raise UsersError("User status could not be updated.", 503) from error


def update_user_verified(actor: OwnerUser, user_id: str, email_verified: bool) -> dict:
    # Manual verified toggles are ignored; nickname presence drives verification.
    _ = email_verified

    if current_app.config.get("TESTING"):
        target = OwnerUser.query.filter_by(id=user_id).first()
        if not target:
            raise UsersError("User was not found.", 404)
        if (target.role or "").lower() == "admin":
            raise UsersError("Admin accounts cannot be changed here.", 403)
        nickname = _nickname_value(target.nickname)
        target.email_verified = bool(nickname)
        if target.email_verified and target.status == "pending_verification":
            target.status = "active"
        target.updated_at = utcnow()
        db.session.commit()
        flags = evaluate_user_flags(
            nickname=nickname,
            last_activity=target.last_login_at or target.updated_at or target.created_at,
        )
        return {
            "id": str(target.id),
            "is_active": flags["is_active"],
            "status": "active" if flags["is_active"] else "inactive",
            "email_verified": flags["email_verified"],
            "has_nickname": flags["has_nickname"],
        }

    try:
        _enable_trusted_user_write()
        directory_role = _directory_role(user_id)
        target = _find_customer_user(user_id)

        if directory_role is None and target is None:
            raise UsersError("User was not found.", 404)
        if (directory_role or (target.role if target else "") or "").lower() == "admin":
            raise UsersError("Admin accounts cannot be changed here.", 403)

        email = (target.email if target else None) or db.session.execute(
            text("select lower(trim(email)) from public.users where id::text = :id limit 1"),
            {"id": str(user_id)},
        ).scalar()

        nickname = _nickname_value(
            getattr(target, "nickname", None),
            db.session.execute(
                text(
                    """
                    select coalesce(nickname, '')
                    from public.users
                    where id::text = :id
                       or (:email <> '' and lower(trim(email)) = :email)
                    order by case when id::text = :id then 0 else 1 end
                    limit 1
                    """
                ),
                {
                    "id": str(user_id),
                    "email": normalize_email(email or "") if email else "",
                },
            ).scalar(),
        )
        verified = bool(nickname)

        if target is not None:
            target.email_verified = verified
            if verified and target.status == "pending_verification":
                target.status = "active"
            target.updated_at = utcnow()
            db.session.flush()

        try:
            _apply_public_verified(user_id, verified, email=email)
        except UsersError:
            if directory_role is not None or target is None:
                raise
        db.session.commit()

        flags = evaluate_user_flags(
            nickname=nickname,
            last_activity=(
                getattr(target, "last_login_at", None)
                or getattr(target, "updated_at", None)
                or getattr(target, "created_at", None)
            ),
        )
        return {
            "id": str(user_id),
            "is_active": flags["is_active"],
            "status": "active" if flags["is_active"] else "inactive",
            "email_verified": flags["email_verified"],
            "has_nickname": flags["has_nickname"],
        }
    except UsersError:
        db.session.rollback()
        raise
    except SQLAlchemyError as error:
        db.session.rollback()
        raise UsersError("Email verification could not be updated.", 503) from error


def delete_user(actor: OwnerUser, user_id: str) -> None:
    """Permanently remove a directory + portal user (not admin, not self)."""
    if str(actor.id) == str(user_id):
        raise UsersError("You cannot delete your own account here.", 403)

    uid = str(user_id)

    if current_app.config.get("TESTING"):
        target = OwnerUser.query.filter_by(id=uid).first()
        if not target:
            raise UsersError("User was not found.", 404)
        if (target.role or "").lower() == "admin":
            raise UsersError("Admin accounts cannot be deleted here.", 403)
        db.session.delete(target)
        db.session.commit()
        return

    try:
        _enable_trusted_user_write()
        directory_role = _directory_role(uid)
        target = _find_customer_user(uid)

        if directory_role is None and target is None:
            raise UsersError("User was not found.", 404)
        if (directory_role or (target.role if target else "") or "").lower() == "admin":
            raise UsersError("Admin accounts cannot be deleted here.", 403)

        # Use SQL (not ORM delete) so FK children and sync triggers behave correctly.
        # ORM session.delete() fails when verifications/devices still point at the user.
        for sql in (
            "delete from customer.email_verifications where user_id::text = :id",
            "delete from customer.trusted_devices where user_id::text = :id",
            "delete from customer.classifications where user_id::text = :id",
        ):
            try:
                with db.session.begin_nested():
                    db.session.execute(text(sql), {"id": uid})
            except SQLAlchemyError:
                # Optional/missing table — ignore and continue.
                pass

        db.session.execute(
            text("delete from customer.users where id::text = :id"),
            {"id": uid},
        )

        # Directory row: sync trigger only removes source='customer'; clear any leftover.
        db.session.execute(
            text(
                """
                delete from public.users
                where id::text = :id
                  and role::text <> 'admin'
                """
            ),
            {"id": uid},
        )
        still_there = db.session.execute(
            text("select 1 from public.users where id::text = :id limit 1"),
            {"id": uid},
        ).first()
        portal_left = db.session.execute(
            text("select 1 from customer.users where id::text = :id limit 1"),
            {"id": uid},
        ).first()
        if still_there or portal_left:
            raise UsersError(
                "User could not be fully deleted (database blocked the remove).",
                503,
            )

        db.session.commit()
    except UsersError:
        db.session.rollback()
        raise
    except SQLAlchemyError as error:
        db.session.rollback()
        current_app.logger.exception("delete_user failed for %s", uid)
        detail = str(getattr(error, "orig", None) or error)
        # Keep flash short; log has the full driver message.
        if "foreign key" in detail.lower():
            raise UsersError(
                "User could not be deleted because related records still exist.",
                503,
            ) from error
        raise UsersError("User could not be deleted.", 503) from error


def find_user_email(user_id: str) -> str | None:
    row = OwnerUser.query.filter_by(id=user_id).first()
    if row:
        return normalize_email(row.email)
    return None


def list_recent_classifications(
    limit: int | None = None,
    *,
    page: int = 1,
    per_page: int | None = None,
    date_preset: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    fabric: str | None = None,
    search_date: str | None = None,
) -> dict:
    empty = {"items": [], "total": 0, "page": 1, "pages": 1, "per_page": per_page or limit or 10}
    if current_app.config.get("TESTING"):
        return empty

    page = max(1, int(page or 1))
    if per_page is None:
        per_page = int(limit or 10)
    per_page = min(100, max(1, int(per_page)))

    clauses = ["1=1"]
    params: dict = {"limit": per_page, "offset": (page - 1) * per_page}
    preset = (date_preset or "").strip().lower()
    if preset == "today":
        clauses.append("c.created_at::date = (timezone('utc', now()))::date")
    elif preset in {"7d", "last_7_days"}:
        clauses.append("c.created_at >= timezone('utc', now()) - interval '7 days'")
    elif preset in {"30d", "last_30_days"}:
        clauses.append("c.created_at >= timezone('utc', now()) - interval '30 days'")
    if date_from:
        clauses.append("c.created_at::date >= cast(:date_from as date)")
        params["date_from"] = date_from
    if date_to:
        clauses.append("c.created_at::date <= cast(:date_to as date)")
        params["date_to"] = date_to
    if search_date:
        clauses.append("c.created_at::date = cast(:search_date as date)")
        params["search_date"] = search_date
    if fabric:
        key = fabric.strip().lower().replace("ñ", "n")
        if key == "pina":
            clauses.append(
                "(lower(replace(coalesce(c.display_name, c.predicted_label), 'ñ', 'n')) like '%pina%')"
            )
        else:
            clauses.append(
                "lower(coalesce(c.display_name, c.predicted_label)) like :fabric_like"
            )
            params["fabric_like"] = f"%{key}%"

    where_sql = " and ".join(clauses)
    try:
        total = db.session.execute(
            text(
                f"""
                select count(*)::int
                from public.classifications c
                where {where_sql}
                """
            ),
            params,
        ).scalar() or 0
        pages = max(1, (int(total) + per_page - 1) // per_page)
        page = min(page, pages)
        params["offset"] = (page - 1) * per_page
        rows = db.session.execute(
            text(
                f"""
                select
                  c.id::text as id,
                  coalesce(c.display_name, c.predicted_label) as predicted_label,
                  c.confidence::float as confidence,
                  coalesce(c.file_name, c.image_reference, c.image_path) as image_name,
                  case
                    when c.image_path like 'https://%' then c.image_path
                    when c.image_reference like 'https://%' then c.image_reference
                    else null
                  end as image_url,
                  c.user_id::text as user_id,
                  coalesce(u.email, c.user_id::text) as email,
                  to_char(c.created_at at time zone 'UTC', 'Mon DD, YYYY') as created_at
                from public.classifications c
                left join customer.users u on u.id = c.user_id::text
                where {where_sql}
                order by c.created_at desc nulls last
                limit :limit offset :offset
                """
            ),
            params,
        ).mappings().all()
        return {
            "items": [dict(r) for r in rows],
            "total": int(total),
            "page": page,
            "pages": pages,
            "per_page": per_page,
        }
    except SQLAlchemyError:
        db.session.rollback()
        return empty


def delete_classification(classification_id: str) -> None:
    """Owner history: delete any classification row by id (and Cloudinary image)."""
    row_id = str(classification_id or "").strip()
    if not row_id:
        raise UsersError("Missing classification id.")
    try:
        existing = db.session.execute(
            text(
                """
                select id::text as id, image_path, file_name
                from public.classifications
                where id = cast(:id as uuid)
                """
            ),
            {"id": row_id},
        ).mappings().first()
        if existing is None:
            raise UsersError("That classification was not found.")

        # Best-effort Cloudinary cleanup before removing the DB row.
        try:
            from app.services.cloudinary_service import delete_classification_image

            delete_classification_image(
                image_path=existing.get("image_path"),
                classification_id=existing.get("id") or row_id,
                filename=existing.get("file_name"),
            )
        except Exception:
            current_app.logger.exception(
                "cloudinary_delete_ignored classification_id=%s", row_id
            )

        result = db.session.execute(
            text(
                """
                delete from public.classifications
                where id = cast(:id as uuid)
                returning id
                """
            ),
            {"id": row_id},
        ).first()
        if result is None:
            db.session.rollback()
            raise UsersError("That classification was not found.")
        db.session.commit()
    except UsersError:
        raise
    except SQLAlchemyError as error:
        db.session.rollback()
        raise UsersError("Could not delete that classification.") from error
