"""Phase 3: convert a dataset tree to WebP in a separate output directory.

Never modifies or deletes source images. Does not retrain or switch production
training paths automatically.

Examples (from repo root):

  # Inventory + size sample estimate (no writes)
  python ml/scripts/convert_dataset_to_webp.py --dry-run --estimate-sample 40

  # Write WebP copies beside the live dataset
  python ml/scripts/convert_dataset_to_webp.py --execute

  python ml/scripts/convert_dataset_to_webp.py \\
    --source ml/data/main_classifier \\
    --output ml/data/main_classifier_webp \\
    --execute --quality 90
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.image_processing.bulk import convert_dataset_tree, write_report
from shared.image_processing.settings import WebPSettings


def main() -> int:
    parser = argparse.ArgumentParser(description="Bulk-convert dataset images to WebP.")
    parser.add_argument(
        "--source",
        type=Path,
        default=REPO_ROOT / "ml" / "data" / "main_classifier",
        help="Source dataset root (class subfolders).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "ml" / "data" / "main_classifier_webp",
        help="Destination root for .webp copies (must differ from source).",
    )
    parser.add_argument("--quality", type=int, default=90)
    parser.add_argument("--method", type=int, default=6)
    parser.add_argument("--lossless", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover files only (default unless --execute).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write WebP files under --output.",
    )
    parser.add_argument(
        "--estimate-sample",
        type=int,
        default=40,
        help="In dry-run, encode this many images to project storage savings.",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Overwrite existing .webp outputs.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="JSON report path (default under ml/reports/).",
    )
    args = parser.parse_args()

    dry_run = not bool(args.execute)
    if args.dry_run:
        dry_run = True

    settings = WebPSettings(
        quality=int(args.quality),
        method=int(args.method),
        lossless=bool(args.lossless),
    )
    report = convert_dataset_tree(
        args.source,
        args.output,
        settings=settings,
        dry_run=dry_run,
        skip_existing=not args.no_skip_existing,
        estimate_sample=int(args.estimate_sample) if dry_run else 0,
        log=lambda m: print(m, flush=True),
    )

    stamp = "dry_run" if dry_run else "execute"
    report_path = args.report or (
        REPO_ROOT / "ml" / "reports" / f"webp_dataset_conversion_{stamp}.json"
    )
    write_report(report, report_path)
    print(json.dumps(report.to_dict(), indent=2))
    print(f"Report written: {report_path}")
    if dry_run:
        print("Dry-run only. Re-run with --execute to write WebP copies.")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
