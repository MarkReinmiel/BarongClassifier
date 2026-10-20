"""Look up accounts in Supabase public.users."""

from __future__ import annotations

from flask import current_app
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import OwnerUser
from app.utils.validators import normalize_email


def find_public_user_by_email(email: str) -> dict | None:
    normalized = normalize_email(email)
    if not normalized:
        return None

    if current_app.config.get("TESTING"):
        row = OwnerUser.query.filter_by(email=normalized).first()
        if not row:
            return None
        return {
            "id": str(row.id),
            "email": row.email,
            "role": row.role,
            "status": row.status,
            "source": "customer",
            "is_active": row.is_active,
            "email_verified": row.email_verified,
        }

    try:
        result = db.session.execute(
            text(
                """
                select
                  id::text as id,
                  email,
                  role::text as role,
                  status,
                  source,
                  is_active,
                  email_verified
                from public.users
                where lower(trim(email)) = :email
                limit 1
                """
            ),
            {"email": normalized},
        ).mappings().first()
    except SQLAlchemyError:
        db.session.rollback()
        row = OwnerUser.query.filter_by(email=normalized).first()
        if not row:
            return None
        return {
            "id": str(row.id),
            "email": row.email,
            "role": row.role,
            "status": row.status,
            "source": "customer",
            "is_active": row.is_active,
            "email_verified": row.email_verified,
        }

    return dict(result) if result else None
