"""Multi-section onboarding tour state (customer portal)."""

from __future__ import annotations

import json

from flask import session
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import CustomerUser, utcnow

SECTIONS = ("main", "classify", "textile", "history", "profile")

_DEFAULT_PROGRESS = {key: False for key in SECTIONS}


def _parse_progress(raw: str | None) -> dict[str, bool]:
    data = dict(_DEFAULT_PROGRESS)
    if not raw:
        return data
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            for key in SECTIONS:
                if key in parsed:
                    data[key] = bool(parsed[key])
            # Accounts saved before the classify section existed should not re-tour it.
            if "classify" not in parsed and any(
                bool(parsed.get(k)) for k in ("main", "textile", "history", "profile")
            ):
                data["classify"] = True
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return data


def get_tour_progress(user: CustomerUser | None) -> dict[str, bool]:
    """Return completion flags for each tutorial section."""
    if not user:
        return dict(_DEFAULT_PROGRESS)
    try:
        raw = getattr(user, "tour_progress", None)
        progress = _parse_progress(raw)
        # Legacy fallback: old accounts only had tour_completed.
        if getattr(user, "tour_completed", False) and not any(progress.values()):
            return {key: True for key in SECTIONS}
        if getattr(user, "tour_completed", False):
            progress["main"] = True
        return progress
    except Exception:
        # Missing column / stale mapper — prefer legacy flag over a hard 500.
        try:
            db.session.rollback()
        except Exception:
            pass
        if getattr(user, "tour_completed", False):
            return {key: True for key in SECTIONS}
        return dict(_DEFAULT_PROGRESS)


def section_needs_tour(user: CustomerUser | None, section: str) -> bool:
    if not user or not user.nickname_completed:
        return False
    section = (section or "").strip().lower()
    if section not in SECTIONS:
        return False
    if section == "main" and session.pop("launch_tour", False):
        return True
    progress = get_tour_progress(user)
    # Classify page tour only after the dashboard (main) tour is done.
    if section == "classify":
        return bool(progress.get("main")) and not progress.get("classify", False)
    return not progress.get(section, False)


def should_launch_tour(user: CustomerUser | None) -> bool:
    """Back-compat helper for the dashboard (main) tour."""
    return section_needs_tour(user, "main")


def mark_section_completed(user: CustomerUser, section: str) -> dict[str, bool]:
    """Persist one section as done; returns the full progress map."""
    section = (section or "").strip().lower()
    if section not in SECTIONS:
        raise ValueError("Unknown tour section.")
    progress = get_tour_progress(user)
    progress[section] = True
    user.tour_progress = json.dumps(progress)
    if section == "main" or all(progress.values()):
        user.tour_completed = True
    user.updated_at = utcnow()
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return progress


def mark_tour_completed(user: CustomerUser) -> None:
    """Back-compat: mark the main dashboard tour done."""
    mark_section_completed(user, "main")


def flag_tour_after_nickname() -> None:
    """Call once when nickname is first saved — starts the main home tour."""
    session["launch_tour"] = True
