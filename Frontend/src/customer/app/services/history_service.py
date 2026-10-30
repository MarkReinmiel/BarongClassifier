"""Classification history scoped to the authenticated user."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.models import Classification, CustomerUser

_FABRIC_ALIASES = {
    "pina": ("pina", "piña", "Piña", "Pina"),
    "piña": ("pina", "piña", "Piña", "Pina"),
    "jusi": ("jusi", "Jusi"),
    "cocoon": ("cocoon", "Cocoon"),
}


def _date_cutoff(preset: str) -> datetime | None:
    key = (preset or "").strip().lower()
    now = datetime.now(timezone.utc)
    if key == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if key in {"7d", "last_7_days"}:
        return now - timedelta(days=7)
    if key in {"30d", "last_30_days"}:
        return now - timedelta(days=30)
    return None


def list_for_user(
    user: CustomerUser,
    *,
    fabric: str | None = None,
    date_preset: str | None = None,
    page: int = 1,
    per_page: int = 10,
) -> dict:
    page = max(1, int(page or 1))
    per_page = min(100, max(1, int(per_page or 10)))
    query = Classification.query.filter_by(user_id=user.id)

    fabric = (fabric or "").strip()
    if fabric:
        aliases = _FABRIC_ALIASES.get(fabric.lower(), (fabric,))
        query = query.filter(
            or_(
                Classification.predicted_label.in_(aliases),
                Classification.display_name.in_(aliases),
            )
        )

    cutoff = _date_cutoff(date_preset or "")
    if cutoff is not None:
        query = query.filter(Classification.created_at >= cutoff)

    query = query.order_by(Classification.created_at.desc())
    total = query.count()
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


def get_owned(user: CustomerUser, classification_id: str) -> Classification | None:
    return Classification.query.filter_by(id=classification_id, user_id=user.id).first()
