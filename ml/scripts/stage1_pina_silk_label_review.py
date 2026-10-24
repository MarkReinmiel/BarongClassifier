"""Stage 1 — Piña Silk dataset inspection and label-review scaffolding.

Does NOT assign textile labels from folder/filename. All rows start as:
  label=uncertain, verification_status=pending_review
unless the file is unreadable (excluded) or an exact duplicate of an earlier file
(flagged in review_notes; still pending_review, excluded from training hints).

Writes:
  ml/reports/pina_silk_label_review.csv
  ml/reports/pina_silk_contact_sheet.jpg  (if Pillow available)
  ml/reports/PINA_SILK_LABEL_REVIEW_REPORT.md
"""

from __future__ import annotations

import csv
import hashlib
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "ml" / "data" / "staging" / "pia_silk"
REPORTS = ROOT / "ml" / "reports"
IMG_EXT = {".jpg", ".jpeg", ".jpe", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def image_id_for(path: Path, digest: str) -> str:
    stem = path.stem.encode("ascii", "ignore").decode("ascii") or "img"
    stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)[:40]
    return f"{digest[:12]}_{stem}"


def probe(path: Path) -> dict:
    meta = {
        "readable": False,
        "width": None,
        "height": None,
        "format": None,
        "error": "",
    }
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            meta["width"], meta["height"] = im.size
            meta["format"] = im.format or path.suffix.lstrip(".").upper()
            meta["readable"] = True
    except (UnidentifiedImageError, OSError, ValueError) as err:
        meta["error"] = f"{type(err).__name__}: {err}"
    return meta


def build_contact_sheet(paths: list[Path], out: Path, thumb: int = 160, cols: int = 6) -> Path | None:
    readable = []
    for p in paths:
        try:
            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((thumb, thumb))
                readable.append((p.name, im.copy()))
        except Exception:
            continue
    if not readable:
        return None
    rows = math.ceil(len(readable) / cols)
    label_h = 18
    sheet = Image.new("RGB", (cols * thumb, rows * (thumb + label_h)), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for i, (name, im) in enumerate(readable):
        r, c = divmod(i, cols)
        x, y = c * thumb, r * (thumb + label_h)
        sheet.paste(im, (x + (thumb - im.width) // 2, y + (thumb - im.height) // 2))
        draw.text((x + 2, y + thumb + 2), name[:22], fill=(20, 20, 20), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    return out


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    if not STAGING.is_dir():
        raise SystemExit(f"Missing staging folder: {STAGING}")

    files = sorted(
        p for p in STAGING.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXT
    )
    all_files = sorted(p for p in STAGING.rglob("*") if p.is_file())
    non_images = [p for p in all_files if p.suffix.lower() not in IMG_EXT]

    rows: list[dict] = []
    by_hash: dict[str, list[str]] = defaultdict(list)

    for path in files:
        digest = sha256_file(path)
        info = probe(path)
        iid = image_id_for(path, digest)
        by_hash[digest].append(str(path))

        if not info["readable"]:
            label = "uncertain"
            status = "excluded"
            notes = f"Unreadable image. {info['error']}".strip()
        else:
            label = "uncertain"
            status = "pending_review"
            notes = (
                "Folder/filename NOT used as material label. "
                "Awaiting manual textile verification (pina_silk | pina | other | uncertain)."
            )

        rows.append(
            {
                "image_id": iid,
                "filename": path.name,
                "source_path": str(path),
                "rel_path": str(path.relative_to(STAGING)).replace("\\", "/"),
                "label": label,
                "verification_status": status,
                "review_notes": notes,
                "sha256": digest,
                "width": info["width"] or "",
                "height": info["height"] or "",
                "format": info["format"] or "",
                "readable": info["readable"],
                "bytes": path.stat().st_size,
                "source_subdir": path.parent.name,
            }
        )

    # Flag exact duplicates (keep first occurrence as primary; others noted).
    first_of: dict[str, str] = {}
    exact_dup_count = 0
    for row in rows:
        dig = row["sha256"]
        if dig not in first_of:
            first_of[dig] = row["image_id"]
            row["is_exact_duplicate"] = False
            row["duplicate_of"] = ""
        else:
            exact_dup_count += 1
            row["is_exact_duplicate"] = True
            row["duplicate_of"] = first_of[dig]
            row["review_notes"] = (
                f"Exact duplicate of {first_of[dig]}. Do not inflate training counts. "
                + row["review_notes"]
            )
            if row["verification_status"] == "pending_review":
                row["verification_status"] = "excluded"
                row["label"] = "uncertain"

    # Near-duplicate heuristic: same filename stem across subdirs, or identical WxH + close size
    size_groups: dict[tuple, list[str]] = defaultdict(list)
    for row in rows:
        if not row["readable"]:
            continue
        key = (row["width"], row["height"], row["bytes"])
        size_groups[key].append(row["image_id"])
    near_flags = 0
    for row in rows:
        if not row["readable"] or row["is_exact_duplicate"]:
            continue
        key = (row["width"], row["height"], row["bytes"])
        peers = [i for i in size_groups[key] if i != row["image_id"]]
        if peers:
            near_flags += 1
            row["review_notes"] += (
                f" Possible near-duplicate peers (same WxH+bytes): {', '.join(peers[:3])}."
            )

    csv_path = REPORTS / "pina_silk_label_review.csv"
    fieldnames = [
        "image_id",
        "filename",
        "source_path",
        "label",
        "verification_status",
        "review_notes",
        "sha256",
        "rel_path",
        "source_subdir",
        "width",
        "height",
        "format",
        "readable",
        "bytes",
        "is_exact_duplicate",
        "duplicate_of",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    sheet_path = REPORTS / "pina_silk_contact_sheet.jpg"
    sheet = build_contact_sheet([Path(r["source_path"]) for r in rows if r["readable"]], sheet_path)

    readable_n = sum(1 for r in rows if r["readable"])
    pending_n = sum(1 for r in rows if r["verification_status"] == "pending_review")
    excluded_n = sum(1 for r in rows if r["verification_status"] == "excluded")
    unique_hashes = len({r["sha256"] for r in rows})
    by_subdir: dict[str, int] = defaultdict(int)
    for r in rows:
        by_subdir[r["source_subdir"]] += 1

    report = REPORTS / "PINA_SILK_LABEL_REVIEW_REPORT.md"
    lines = [
        "# Piña Silk Label Review Report (Stage 1)",
        "",
        f"**Generated (UTC):** {datetime.now(timezone.utc).isoformat()}",
        f"**Staging root:** `{STAGING}`",
        "",
        "## Enumeration",
        "",
        f"- Total files under staging: **{len(all_files)}**",
        f"- Image files (by extension): **{len(files)}**",
        f"- Non-image files: **{len(non_images)}**",
        f"- Readable images: **{readable_n}**",
        f"- Unique SHA-256 hashes: **{unique_hashes}**",
        f"- Exact duplicate images (extra copies): **{exact_dup_count}**",
        f"- Rows flagged for same WxH+bytes peers: **{near_flags}**",
        "",
        "### By subfolder",
        "",
    ]
    for name, count in sorted(by_subdir.items(), key=lambda x: x[0]):
        lines.append(f"- `{name}`: {count}")
    lines += [
        "",
        "## Label policy (enforced in this stage)",
        "",
        "- **No automatic material labels** from folder or filename.",
        "- Every readable, non-duplicate row starts as `label=uncertain`, `verification_status=pending_review`.",
        "- Exact duplicates are `verification_status=excluded` so they cannot inflate training.",
        "- Unreadable files are `excluded`.",
        "",
        "## Review status counts",
        "",
        f"- `pending_review`: **{pending_n}**",
        f"- `excluded`: **{excluded_n}**",
        f"- `verified`: **0** (none — manual review required)",
        "",
        "## Allowed values for manual fill-in",
        "",
        "| Field | Values |",
        "|---|---|",
        "| `label` | `pina_silk`, `pina`, `other`, `uncertain` |",
        "| `verification_status` | `pending_review`, `verified`, `excluded` |",
        "",
        "## Artifacts",
        "",
        f"- Manifest: `{csv_path}`",
        f"- Contact sheet: `{sheet_path if sheet else 'not generated'}`",
        "",
        "## STOP — manual confirmation required",
        "",
        "Variant training must **not** begin until this CSV is filled with verified labels.",
        "",
        "How to complete review:",
        "",
        "1. Open the contact sheet and/or each `source_path` in the CSV.",
        "2. For each pending row, set `label` to the true textile class.",
        "3. Set `verification_status=verified` only when a human (textile-knowledgeable) confirms the material.",
        "4. Use `excluded` for bad crops, wrong material, or keep duplicates excluded.",
        "5. Leave unresolved rows as `uncertain` / `pending_review` — they stay out of training.",
        "",
        "## Adequacy gate (before Stage 2 training)",
        "",
        "After review, report:",
        "",
        "- Count of `verified` + `pina_silk`",
        "- Count of `verified` + `pina` (ordinary) available for the binary head",
        "- Number of independent physical samples if known",
        "",
        "If verified Piña Silk is inadequate for a meaningful train/val/test split, keep production",
        "behavior (variant undetermined) and collect more verified samples.",
        "",
        "## Next stages blocked",
        "",
        "- Stage 2–4 variant training / evaluation",
        "- Stage 5–7 deployment and removal of hardcoded `undetermined`",
        "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")

    print(f"Images found: {len(files)} (readable={readable_n})")
    print(f"Unique hashes: {unique_hashes}; exact dups: {exact_dup_count}")
    print(f"Pending review: {pending_n}; excluded: {excluded_n}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {report}")
    if sheet:
        print(f"Wrote {sheet}")
    print("STOP: fill pina_silk_label_review.csv before variant training.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
