"""Classification history scoped to the authenticated user."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Classification, CustomerUser


class HistoryError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code

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
    # Match both string and raw UUID forms stored in public.classifications.user_id
    uid = str(user.id)
    query = Classification.query.filter(Classification.user_id.in_([uid, user.id]))

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


def stats_for_user(user: CustomerUser) -> dict:
    """Summary cards for History: total, most common label, average confidence."""
    uid = str(user.id)
    rows = (
        Classification.query.filter(Classification.user_id.in_([uid, user.id]))
        .order_by(Classification.created_at.desc())
        .all()
    )
    total = len(rows)
    if not total:
        return {
            "total": 0,
            "most_common": "—",
            "avg_confidence": None,
            "avg_confidence_label": "—",
        }

    counts: dict[str, int] = {}
    conf_sum = 0.0
    for row in rows:
        label = (row.display_name or row.predicted_label or "").strip() or "—"
        counts[label] = counts.get(label, 0) + 1
        try:
            conf_sum += float(row.confidence or 0.0)
        except (TypeError, ValueError):
            pass

    most_common = max(counts.items(), key=lambda item: item[1])[0]
    avg = conf_sum / total if total else 0.0
    # confidence may already be 0–1 or 0–100
    if avg > 1.5:
        avg_pct = avg
    else:
        avg_pct = avg * 100.0
    return {
        "total": total,
        "most_common": most_common,
        "avg_confidence": avg_pct,
        "avg_confidence_label": f"{round(avg_pct):.0f}%",
    }


def delete_for_user(user: CustomerUser, classification_id: str) -> None:
    """Delete one classification owned by the signed-in customer."""
    if not user or not user.id:
        raise HistoryError("Sign in again.", 401)
    row_id = str(classification_id or "").strip()
    if not row_id:
        raise HistoryError("Missing classification id.")
    uid = str(user.id)
    row = (
        Classification.query.filter(
            Classification.id == row_id,
            Classification.user_id.in_([uid, user.id]),
        )
        .first()
    )
    if row is None:
        raise HistoryError("That classification was not found.", 404)
    try:
        db.session.delete(row)
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise HistoryError("Could not delete that classification.", 503) from error


def format_history_when_parts(created_at) -> tuple[str, str]:
    """Return (day_label, time_label) like ('Today', '4:15 PM')."""
    if not created_at:
        return ("—", "")
    try:
        now = datetime.now(timezone.utc)
        when = created_at
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        local = when.astimezone()
        today = now.astimezone().date()
        day = local.date()
        time_part = local.strftime("%I:%M %p").lstrip("0")
        if day == today:
            return ("Today", time_part)
        if (today - day).days == 1:
            return ("Yesterday", time_part)
        return (local.strftime("%b %d, %Y"), time_part)
    except Exception:
        return ("—", "")


def get_owned(user: CustomerUser, classification_id: str) -> Classification | None:
    return Classification.query.filter_by(id=classification_id, user_id=user.id).first()
