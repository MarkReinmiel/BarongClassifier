"""Apply model major/revision migration."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / "Frontend" / "src" / "owner"
sys.path.insert(0, str(OWNER))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from sqlalchemy import text  # noqa: E402

SQL_PATH = ROOT / "supabase" / "migrations" / "20261106000300_model_version_revisions.sql"


def main() -> int:
    app = create_app()
    sql = SQL_PATH.read_text(encoding="utf-8")
    with app.app_context():
        try:
            db.session.execute(text(sql))
            db.session.commit()
            print("migration_ok")
        except Exception as error:
            db.session.rollback()
            print(f"migration_error {type(error).__name__}: {error}")
            return 1
        rows = db.session.execute(
            text(
                """
                select version_label, major_version, revision_number, is_production, status
                from public.model_versions
                order by major_version, revision_number
                """
            )
        ).mappings().all()
        for row in rows:
            print(dict(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
