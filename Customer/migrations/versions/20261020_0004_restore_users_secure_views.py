"""Restore public.users + secure users_directory; seed Flask owner.

Revision ID: 20261020_0004
Revises: 20261020_0003
Create Date: 2026-10-20

- Recreate public.users (accidentally dropped; Auth mirror, no password column)
- Recreate public.users_directory with security_invoker (fixes Security Definer advisor)
- Revoke anon/authenticated API access on directory / portal views
- Upsert owner into customer.users with scrypt password_hash
"""

from alembic import op
import sqlalchemy as sa

revision = "20261020_0004"
down_revision = "20261020_0003"
branch_labels = None
depends_on = None

# Pre-hashed with werkzeug scrypt (plaintext is not stored in this file).
OWNER_EMAIL = "barongclassifier@gmail.com"
OWNER_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
OWNER_PASSWORD_HASH = (
    "scrypt:32768:8:1$kyDUmFZlNRaJFsTw$"
    "9bd44e6685a5590fcc6fcfcda06ddbb6df836106b48b958f118846596cd39403"
    "167b9dee1b1bdf9a7e0a5f3cb98865499ac41fac3466dedc760ff22f2601b100"
)


def upgrade():
    # Drop API-exposed portal views (Security Definer / invoker warnings).
    op.execute("drop view if exists public.customer_portal_classifications cascade")
    op.execute("drop view if exists public.customer_portal_trusted_devices cascade")
    op.execute("drop view if exists public.customer_portal_email_verifications cascade")
    op.execute("drop view if exists public.customer_portal_users cascade")
    op.execute("drop view if exists public.portal_classifications cascade")
    op.execute("drop view if exists public.email_verifications cascade")
    op.execute("drop view if exists public.trusted_devices cascade")
    op.execute("drop view if exists public.users_directory cascade")

    # Restore public.users (Frontend Auth directory).
    op.execute(
        """
        create table if not exists public.users (
          id uuid primary key references auth.users (id) on delete cascade,
          email text,
          full_name text not null default '',
          role public.app_role not null default 'customer',
          is_active boolean not null default true,
          email_verified boolean not null default false,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          last_sign_in_at timestamptz
        );

        create unique index if not exists users_email_unique on public.users (email);

        alter table public.users enable row level security;

        drop policy if exists "Users can read own user row" on public.users;
        create policy "Users can read own user row"
          on public.users for select to authenticated
          using (auth.uid() = id or public.is_admin());

        create or replace function public.sync_public_user()
        returns trigger
        language plpgsql
        security definer
        set search_path = public
        as $$
        begin
          insert into public.users (
            id, email, full_name, role, is_active, email_verified,
            created_at, updated_at, last_sign_in_at
          )
          values (
            new.id,
            new.email,
            coalesce(new.full_name, ''),
            coalesce(new.role, 'customer'),
            coalesce(new.is_active, true),
            coalesce(new.email_verified, false),
            coalesce(new.created_at, now()),
            now(),
            new.last_login_at
          )
          on conflict (id) do update
            set email = excluded.email,
                full_name = excluded.full_name,
                role = excluded.role,
                is_active = excluded.is_active,
                email_verified = excluded.email_verified,
                updated_at = now(),
                last_sign_in_at = excluded.last_sign_in_at;
          return new;
        end;
        $$;

        revoke all on function public.sync_public_user() from public, anon, authenticated;

        drop trigger if exists profiles_sync_users on public.profiles;
        create trigger profiles_sync_users
          after insert or update on public.profiles
          for each row execute function public.sync_public_user();

        insert into public.users (
          id, email, full_name, role, is_active, email_verified,
          created_at, updated_at, last_sign_in_at
        )
        select
          profiles.id,
          profiles.email,
          coalesce(profiles.full_name, ''),
          profiles.role,
          profiles.is_active,
          profiles.email_verified,
          profiles.created_at,
          now(),
          auth_users.last_sign_in_at
        from public.profiles as profiles
        join auth.users as auth_users on auth_users.id = profiles.id
        on conflict (id) do update
          set email = excluded.email,
              full_name = excluded.full_name,
              role = excluded.role,
              is_active = excluded.is_active,
              email_verified = excluded.email_verified,
              last_sign_in_at = excluded.last_sign_in_at,
              updated_at = now();
        """
    )

    # Unified directory: security_invoker + no Data API grants.
    op.execute(
        """
        create or replace view public.users_directory
        with (security_invoker = true)
        as
        select
          id::text as id,
          email,
          full_name,
          role::text as role,
          case when is_active then 'active' else 'disabled' end as status,
          is_active,
          email_verified,
          created_at,
          updated_at,
          last_sign_in_at as last_login_at,
          'auth'::text as source
        from public.users
        union all
        select
          id,
          email,
          full_name,
          role,
          status,
          is_active,
          email_verified,
          created_at,
          updated_at,
          last_login_at,
          'customer'::text as source
        from customer.users;

        comment on view public.users_directory is
          'Auth public.users + Flask customer.users. security_invoker; not exposed to anon/authenticated.';

        revoke all on public.users_directory from public, anon, authenticated;
        grant select on public.users_directory to postgres;
        """
    )

    # Owner account for Flask Customer portal (password_hash only here).
    op.get_bind().execute(
        sa.text(
            """
            insert into customer.users (
              id, email, password_hash, full_name, role, status,
              email_verified, nickname, nickname_completed, is_active,
              created_at, updated_at
            )
            values (
              :id, :email, :password_hash, 'Owner', 'owner', 'active',
              true, 'Owner', true, true, now(), now()
            )
            on conflict (email) do update
              set password_hash = excluded.password_hash,
                  full_name = excluded.full_name,
                  role = 'owner',
                  status = 'active',
                  email_verified = true,
                  nickname = coalesce(customer.users.nickname, 'Owner'),
                  nickname_completed = true,
                  is_active = true,
                  updated_at = now()
            """
        ),
        {
            "id": OWNER_ID,
            "email": OWNER_EMAIL,
            "password_hash": OWNER_PASSWORD_HASH,
        },
    )


def downgrade():
    op.get_bind().execute(
        sa.text("delete from customer.users where lower(email) = lower(:email)"),
        {"email": OWNER_EMAIL},
    )
    op.execute("drop view if exists public.users_directory cascade")
    # Keep public.users on downgrade — Frontend depends on it.
