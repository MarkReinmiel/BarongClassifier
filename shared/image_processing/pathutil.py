"""Ensure the monorepo root is importable so ``shared.*`` resolves."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_root_on_sys_path(start: Path | None = None) -> Path:
    """Insert BarongClassifier repo root on ``sys.path`` if missing.

    Walks parents looking for ``shared/image_processing``.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        marker = candidate / "shared" / "image_processing"
        if marker.is_dir():
            root = str(candidate)
            if root not in sys.path:
                sys.path.insert(0, root)
            return candidate
    raise RuntimeError(
        "Could not locate BarongClassifier repo root (shared/image_processing missing)."
    )
