"""Role checks and a small in-process request limit."""

from __future__ import annotations

import time
from collections import defaultdict

PRIVILEGED_ROLES = {"admin", "owner"}
ASSIGNABLE_ROLES = {"owner", "customer"}


def can_assign_role(actor_role: str, target_is_self: bool, new_role: str) -> bool:
    if actor_role != "admin" or target_is_self:
        return False
    return new_role in ASSIGNABLE_ROLES


def can_view_history(actor_id: str, actor_role: str, owner_id: str) -> bool:
    if actor_role == "admin":
        return True
    return actor_id == owner_id


class RateLimiter:
    def __init__(self, limit: int = 10, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        recent = [stamp for stamp in self.hits[key] if now - stamp < self.window_seconds]
        if len(recent) >= self.limit:
            self.hits[key] = recent
            return False
        recent.append(now)
        self.hits[key] = recent
        return True
