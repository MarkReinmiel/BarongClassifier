# Customer database workflow

## Architecture discovered

- Provider: Supabase PostgreSQL over the **session pooler** (`aws-0-*-pooler.supabase.com:5432`)
- Application schema: `customer` (isolated from Supabase Auth `auth.*` and public app tables)
- Auth for Customer: Flask password hashing (`customer.users.password_hash`), not Supabase Auth
- ORM: Flask-SQLAlchemy
- Migrations: Flask-Migrate / Alembic (version table in `customer.alembic_version`)

Tables (owner / Flask): `customer.users`, `customer.email_verifications`, `customer.trusted_devices`

Classification history (Customer + Owner portals): **`public.classifications`** — same table the Supabase Table Editor shows by default.

Each of those tables has `role` + `status` (aligned with owner `public.users.role`).

`public.users` is the **single account directory** (Auth + Flask). `public.profiles` was dropped — use `users` instead (`must_change_password`, `role`, `status`, `source`).

Portal mirrors (no secret hashes; API revoked for anon/authenticated):
`public.email_verifications`, `public.trusted_devices` — synced from `customer.*`.

Flask passwords stay only on `customer.users.password_hash`.

## Environment

Prefer either:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require
```

or the split `DB_HOST` / `DB_PORT` / `DB_DATABASE` / `DB_USERNAME` / `DB_PASSWORD` / `DB_SSLMODE` keys already used by this project.

Never commit `.env`. Never print connection strings with passwords.

## Commands

```powershell
cd Customer
.\.venv\Scripts\Activate.ps1
$env:FLASK_APP = "app:create_app"
$env:PYTHONPATH = "."

flask db current
flask db history
flask db migrate -m "describe changes"
# Review the generated file under migrations/versions before applying
flask db upgrade
flask routes
python -m pytest -q
```

`flask db migrate` compares **ORM metadata** to the migration environment. It does not automatically pull every remote Supabase change.

## Compare remote schema safely

Sanitized Python audit (no secrets printed):

```powershell
$env:PYTHONPATH = "."
python -c "from sqlalchemy import text; from app import create_app; from app.extensions import db; app=create_app();
ctx=app.app_context(); ctx.push();
print([r[0] for r in db.session.execute(text(\"select table_name from information_schema.tables where table_schema='customer'\")).fetchall()])"
```

Optional `pg_dump` schema-only export (keep credentials out of shell history):

```powershell
pg_dump "$env:DATABASE_URL" --schema=customer --schema-only --no-owner --no-privileges
```

## Safety

- Do not run `db.create_all()` against production as a substitute for migrations.
- Do not use `flask db stamp head` unless the remote schema has been verified to match the migration.
- Autogenerate is limited to the `customer` schema so `public` / `auth` / `private` are not altered.
- RLS is not required for direct server-side SQLAlchemy access; keep DB credentials server-only.
