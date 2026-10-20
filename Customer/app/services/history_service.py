"""Classification history scoped to the authenticated user."""

from __future__ import annotations

from app.models import Classification, CustomerUser


def list_for_user(
    user: CustomerUser,
    *,
    fabric: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict:
    page = max(1, int(page or 1))
    per_page = min(100, max(1, int(per_page or 50)))
    query = Classification.query.filter_by(user_id=user.id)
    fabric = (fabric or "").strip()
    if fabric:
        query = query.filter(Classification.predicted_label == fabric)
    query = query.order_by(Classification.created_at.desc())
    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


def get_owned(user: CustomerUser, classification_id: str) -> Classification | None:
    return Classification.query.filter_by(id=classification_id, user_id=user.id).first()
