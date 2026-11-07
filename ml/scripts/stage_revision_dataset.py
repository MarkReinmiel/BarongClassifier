"""Stage a training revision dataset.

Copies the master folder dataset, merges Owner-approved customer contributions
(deduped by content hash), updates the master with newly seen files, and writes
a snapshot under ml/data/snapshots/<snapshot_id>/ for training.

Same revision slot overwrites its snapshot folder (no _alt / timestamp piles).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

CLASSES = ("cocoon", "jusi", "pina")
IMG_EXT = {".jpg", ".jpeg", ".jpe", ".png", ".webp", ".bmp"}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _index_existing_hashes(root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not root.is_dir():
        return index
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMG_EXT:
            try:
                index[_sha256_file(path)] = path
            except OSError:
                continue
    return index


def _download(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "BarongClassifier-revision-staging/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _guess_ext(url: str, data: bytes) -> str:
    lower = url.lower().split("?", 1)[0]
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        if lower.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def stage_from_plan(plan: dict[str, Any], *, log=print) -> dict[str, Any]:
    """Materialize snapshot + merge new contributions into master. Returns summary."""
    master = Path(plan["master_dataset"])
    snapshot_dir = Path(plan["snapshot_dir"])
    contributions = plan.get("contributions") or []

    for class_name in CLASSES:
        (master / class_name).mkdir(parents=True, exist_ok=True)

    master_index = _index_existing_hashes(master)
    added_to_master = 0
    skipped_dupes = 0
    failed: list[dict[str, str]] = []
    staged: list[dict[str, Any]] = []

    for item in contributions:
        label = item.get("label")
        url = (item.get("image_url") or "").strip()
        if label not in CLASSES or not url:
            continue
        try:
            if url.startswith("http://") or url.startswith("https://"):
                data = _download(url)
            else:
                src = Path(url)
                if not src.is_file():
                    raise FileNotFoundError(f"Local image missing: {url}")
                data = src.read_bytes()
            digest = _sha256_bytes(data)
            if digest in master_index:
                skipped_dupes += 1
                staged.append(
                    {
                        **item,
                        "sha256": digest,
                        "status": "duplicate_skipped",
                        "path": str(master_index[digest]),
                    }
                )
                continue
            ext = _guess_ext(url, data)
            cid = (item.get("classification_id") or "unknown")[:12]
            dest = master / label / f"contrib_{cid}_{digest[:12]}{ext}"
            dest.write_bytes(data)
            master_index[digest] = dest
            added_to_master += 1
            staged.append(
                {
                    **item,
                    "sha256": digest,
                    "status": "added_to_master",
                    "path": str(dest),
                }
            )
            log(f"Added contribution {dest.name} -> {label}")
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
            failed.append(
                {
                    "classification_id": str(item.get("classification_id") or ""),
                    "error": str(error)[:300],
                }
            )
            log(f"Failed contribution {item.get('classification_id')}: {error}")

    if snapshot_dir.exists():
        # Same revision slot: overwrite so retries do not stack ~1.7GB folders.
        log(f"Overwriting existing snapshot at {snapshot_dir}")
        shutil.rmtree(snapshot_dir, ignore_errors=True)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    for class_name in CLASSES:
        src_dir = master / class_name
        dest_dir = snapshot_dir / class_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        if not src_dir.is_dir():
            continue
        for path in src_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMG_EXT:
                rel = path.relative_to(src_dir)
                target = dest_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)

    counts = {
        class_name: sum(
            1
            for p in (snapshot_dir / class_name).rglob("*")
            if p.is_file() and p.suffix.lower() in IMG_EXT
        )
        for class_name in CLASSES
    }
    summary = {
        "snapshot_id": plan.get("snapshot_id"),
        "snapshot_dir": str(snapshot_dir),
        "master_dataset": str(master),
        "display_revision": plan.get("display_revision"),
        "major_version": plan.get("major_version"),
        "revision_number": plan.get("revision_number"),
        "added_to_master": added_to_master,
        "duplicates_skipped": skipped_dupes,
        "failed_count": len(failed),
        "failed": failed,
        "class_counts": counts,
        "total_images": sum(counts.values()),
        "staged": staged,
        "includes_original_training_data": True,
        "includes_previously_approved": True,
        "includes_newly_approved": True,
    }
    (snapshot_dir / "snapshot_manifest.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "staged"}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return summary
