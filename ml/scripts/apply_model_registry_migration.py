"""Apply model registry migration against the Owner app database."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / "Frontend" / "src" / "owner"
sys.path.insert(0, str(OWNER))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from sqlalchemy import text  # noqa: E402

SQL_PATH = ROOT / "supabase" / "migrations" / "20261106000200_model_registry.sql"


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
        tables = db.session.execute(
            text(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                  and table_name in (
                    'model_versions',
                    'training_jobs',
                    'model_evaluations',
                    'model_deployments'
                  )
                order by 1
                """
            )
        ).scalars().all()
        print("tables", list(tables))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
