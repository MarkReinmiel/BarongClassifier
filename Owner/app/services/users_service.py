"""Owner directory views over public.users / customer.users (shared DB)."""

from __future__ import annotations

from flask import current_app
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import OwnerUser, utcnow
from app.utils.validators import normalize_email

ASSIGNABLE = frozenset({"owner", "customer"})


class UsersError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def dashboard_stats() -> dict:
    """Frontend-style overview numbers plus directory counts."""
    stats = {
        "textile_types": 3,
        "model_accuracy": 100,
        "test_images": 39,
        "users_total": 0,
        "owners_total": 0,
        "customers_total": 0,
        "classifications_total": 0,
        "active_users": 0,
    }
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


def list_directory_users() -> list[dict]:
    if current_app.config.get("TESTING"):
        return [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name or u.nickname or "",
                "role": u.role,
                "status": u.status,
                "is_active": bool(u.is_active),
                "email_verified": bool(u.email_verified),
                "source": "customer",
            }
            for u in OwnerUser.query.order_by(OwnerUser.created_at.desc()).all()
        ]

    try:
        rows = db.session.execute(
            text(
                """
                select
                  id::text as id,
                  email,
                  coalesce(full_name, '') as full_name,
                  role::text as role,
                  status,
                  coalesce(is_active, true) as is_active,
                  coalesce(email_verified, false) as email_verified,
                  coalesce(source, '') as source
                from public.users
                order by created_at desc nulls last
                limit 200
                """
            )
        ).mappings().all()
        return [dict(r) for r in rows]
    except SQLAlchemyError:
        db.session.rollback()
        return [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name or "",
                "role": u.role,
                "status": u.status,
                "is_active": bool(u.is_active),
                "email_verified": bool(u.email_verified),
                "source": "customer",
            }
            for u in OwnerUser.query.order_by(OwnerUser.created_at.desc()).limit(200).all()
        ]


def update_user_role(actor: OwnerUser, user_id: str, role: str) -> None:
    role = (role or "").strip().lower()
    if role not in ASSIGNABLE:
        raise UsersError("Role must be owner or customer.")
    if str(actor.id) == str(user_id):
        raise UsersError("You cannot change your own role here.", 403)

    target = OwnerUser.query.filter_by(id=user_id).first()
    if target and (target.role or "").lower() == "admin":
        raise UsersError("Admin accounts cannot be changed here.", 403)

    if target:
        target.role = role
        target.updated_at = utcnow()
        db.session.commit()

    if current_app.config.get("TESTING"):
        return

    try:
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
        if result.rowcount == 0 and not target:
            raise UsersError("User was not found.", 404)
        db.session.commit()
    except UsersError:
        raise
    except SQLAlchemyError as error:
        db.session.rollback()
        if not target:
            raise UsersError("User role could not be updated.", 503) from error


def update_user_status(actor: OwnerUser, user_id: str, is_active: bool) -> None:
    if str(actor.id) == str(user_id):
        raise UsersError("You cannot deactivate your own Owner session here.", 403)

    target = OwnerUser.query.filter_by(id=user_id).first()
    if target and (target.role or "").lower() == "admin":
        raise UsersError("Admin accounts cannot be changed here.", 403)

    if target:
        target.is_active = bool(is_active)
        target.status = "active" if is_active else "disabled"
        target.updated_at = utcnow()
        db.session.commit()

    if current_app.config.get("TESTING"):
        return

    try:
        result = db.session.execute(
            text(
                """
                update public.users
                set is_active = :active,
                    status = case when :active then 'active' else 'disabled' end,
                    updated_at = now()
                where id::text = :id
                  and role::text <> 'admin'
                """
            ),
            {"active": bool(is_active), "id": str(user_id)},
        )
        if result.rowcount == 0 and not target:
            raise UsersError("User was not found.", 404)
        db.session.commit()
    except UsersError:
        raise
    except SQLAlchemyError as error:
        db.session.rollback()
        if not target:
            raise UsersError("User status could not be updated.", 503) from error


def find_user_email(user_id: str) -> str | None:
    row = OwnerUser.query.filter_by(id=user_id).first()
    if row:
        return normalize_email(row.email)
    return None


def list_recent_classifications(
    limit: int = 100,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    fabric: str | None = None,
    search_date: str | None = None,
) -> list[dict]:
    if current_app.config.get("TESTING"):
        return []

    clauses = ["1=1"]
    params: dict = {"limit": int(limit)}
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
        clauses.append("lower(c.predicted_label) = lower(:fabric)")
        params["fabric"] = fabric.strip()

    where_sql = " and ".join(clauses)
    try:
        rows = db.session.execute(
            text(
                f"""
                select
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
                  to_char(c.created_at at time zone 'UTC', 'Mon DD, YYYY HH24:MI') as created_at
                from public.classifications c
                left join customer.users u on u.id = c.user_id::text
                where {where_sql}
                order by c.created_at desc nulls last
                limit :limit
                """
            ),
            params,
        ).mappings().all()
        return [dict(r) for r in rows]
    except SQLAlchemyError:
        db.session.rollback()
        return []
