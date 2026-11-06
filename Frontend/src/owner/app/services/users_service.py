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


def _apply_public_status(user_id: str, active: bool, status_value: str) -> None:
    result = db.session.execute(
        text(
            """
            update public.users
            set is_active = cast(:active as boolean),
                status = :status,
                updated_at = now()
            where id::text = :id
              and role::text <> 'admin'
            """
        ),
        {"active": active, "status": status_value, "id": str(user_id)},
    )
    if result.rowcount == 0:
        raise UsersError("User status could not be updated.", 404)
    verify = db.session.execute(
        text(
            """
            select coalesce(is_active, true) as is_active
            from public.users
            where id::text = :id
            """
        ),
        {"id": str(user_id)},
    ).mappings().first()
    if not verify or bool(verify["is_active"]) != active:
        raise UsersError("User status was blocked by database privileges.", 503)


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


def update_user_status(actor: OwnerUser, user_id: str, is_active: bool) -> None:
    if str(actor.id) == str(user_id):
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

        if target is not None:
            target.is_active = active
            target.status = status_value
            target.updated_at = utcnow()
            db.session.flush()

        if directory_role is not None:
            _apply_public_status(user_id, active, status_value)

        db.session.commit()
    except UsersError:
        db.session.rollback()
        raise
    except SQLAlchemyError as error:
        db.session.rollback()
        raise UsersError("User status could not be updated.", 503) from error


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
