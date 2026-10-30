"""Store all directory data in public.users; drop users_directory view.

Revision ID: 20261020_0005
Revises: 20261020_0004
Create Date: 2026-10-20

Eliminates the public.users_directory VIEW (Security Definer / API advisories).
public.users becomes the single directory table: Auth + Flask portal rows.
Passwords stay only in customer.users.password_hash (never copied to public).
"""

from alembic import op

revision = "20261020_0005"
down_revision = "20261020_0004"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Kill the view that keeps triggering Supabase security warnings.
    op.execute("drop view if exists public.users_directory cascade")
    op.execute("drop view if exists public.customer_portal_users cascade")
    op.execute("drop view if exists public.customer_portal_email_verifications cascade")
    op.execute("drop view if exists public.customer_portal_trusted_devices cascade")
    op.execute("drop view if exists public.customer_portal_classifications cascade")
    op.execute("drop view if exists public.portal_classifications cascade")
    op.execute("drop view if exists public.email_verifications cascade")
    op.execute("drop view if exists public.trusted_devices cascade")

    # 2) Ensure public.users exists, then allow portal UUIDs (drop Auth-only FK).
    op.execute(
        """
        create table if not exists public.users (
          id uuid primary key,
          email text,
          full_name text not null default '',
          role public.app_role not null default 'customer',
          is_active boolean not null default true,
          email_verified boolean not null default false,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          last_sign_in_at timestamptz
        );

        alter table public.users drop constraint if exists users_id_fkey;

        alter table public.users
          add column if not exists status text not null default 'active',
          add column if not exists source text not null default 'auth',
          add column if not exists nickname text,
          add column if not exists nickname_completed boolean not null default false,
          add column if not exists last_login_at timestamptz;

        create unique index if not exists users_email_unique on public.users (email);
        create index if not exists users_source_idx on public.users (source);
        create index if not exists users_status_idx on public.users (status);

        alter table public.users enable row level security;

        drop policy if exists "Users can read own user row" on public.users;
        create policy "Users can read own user row"
          on public.users for select to authenticated
          using (
            (source = 'auth' and auth.uid() = id)
            or public.is_admin()
          );

        -- Never expose directory rows to anon via Data API writes.
        revoke all on table public.users from anon;
        grant select on table public.users to authenticated;
        grant all on table public.users to service_role, postgres;
        """
    )

    # 3) Normalize existing Auth rows already in public.users.
    op.execute(
        """
        update public.users
        set source = coalesce(nullif(source, ''), 'auth'),
            status = case
              when is_active = false then 'disabled'
              when email_verified = false then 'pending_verification'
              else coalesce(nullif(status, ''), 'active')
            end,
            updated_at = now()
        where coalesce(source, 'auth') = 'auth'
           or source is null
           or source = '';
        """
    )

    # 4) Replace directory data: upsert every Flask customer.users row into public.users.
    op.execute(
        """
        insert into public.users (
          id, email, full_name, role, status, source,
          is_active, email_verified, nickname, nickname_completed,
          created_at, updated_at, last_sign_in_at, last_login_at
        )
        select
          cu.id::uuid,
          cu.email,
          coalesce(nullif(trim(cu.full_name), ''), coalesce(cu.nickname, '')),
          case
            when lower(cu.role) in ('admin', 'owner', 'customer')
              then lower(cu.role)::public.app_role
            else 'customer'::public.app_role
          end,
          coalesce(nullif(cu.status, ''), 'active'),
          'customer',
          cu.is_active,
          cu.email_verified,
          cu.nickname,
          cu.nickname_completed,
          cu.created_at,
          cu.updated_at,
          cu.last_login_at,
          cu.last_login_at
        from customer.users cu
        on conflict (id) do update
          set email = excluded.email,
              full_name = excluded.full_name,
              role = excluded.role,
              status = excluded.status,
              source = 'customer',
              is_active = excluded.is_active,
              email_verified = excluded.email_verified,
              nickname = excluded.nickname,
              nickname_completed = excluded.nickname_completed,
              last_sign_in_at = excluded.last_sign_in_at,
              last_login_at = excluded.last_login_at,
              updated_at = now();
        """
    )

    # 5) Keep public.users in sync from profiles (Auth) — no view.
    op.execute(
        """
        create or replace function public.sync_public_user()
        returns trigger
        language plpgsql
        security definer
        set search_path = public
        as $$
        begin
          insert into public.users (
            id, email, full_name, role, status, source,
            is_active, email_verified, created_at, updated_at,
            last_sign_in_at, last_login_at
          )
          values (
            new.id,
            new.email,
            coalesce(new.full_name, ''),
            coalesce(new.role, 'customer'),
            case
              when coalesce(new.is_active, true) = false then 'disabled'
              when coalesce(new.email_verified, false) = false then 'pending_verification'
              else 'active'
            end,
            'auth',
            coalesce(new.is_active, true),
            coalesce(new.email_verified, false),
            coalesce(new.created_at, now()),
            now(),
            new.last_login_at,
            new.last_login_at
          )
          on conflict (id) do update
            set email = excluded.email,
                full_name = excluded.full_name,
                role = excluded.role,
                status = excluded.status,
                source = 'auth',
                is_active = excluded.is_active,
                email_verified = excluded.email_verified,
                last_sign_in_at = excluded.last_sign_in_at,
                last_login_at = excluded.last_login_at,
                updated_at = now();
          return new;
        end;
        $$;

        revoke all on function public.sync_public_user() from public, anon, authenticated;

        drop trigger if exists profiles_sync_users on public.profiles;
        create trigger profiles_sync_users
          after insert or update on public.profiles
          for each row execute function public.sync_public_user();
        """
    )

    # 6) Keep public.users in sync from Flask customer.users (still no password copy).
    op.execute(
        """
        create or replace function public.sync_customer_user_to_public()
        returns trigger
        language plpgsql
        security definer
        set search_path = public, customer
        as $$
        begin
          if tg_op = 'DELETE' then
            delete from public.users
            where id = old.id::uuid and source = 'customer';
            return old;
          end if;

          insert into public.users (
            id, email, full_name, role, status, source,
            is_active, email_verified, nickname, nickname_completed,
            created_at, updated_at, last_sign_in_at, last_login_at
          )
          values (
            new.id::uuid,
            new.email,
            coalesce(nullif(trim(new.full_name), ''), coalesce(new.nickname, '')),
            case
              when lower(new.role) in ('admin', 'owner', 'customer')
                then lower(new.role)::public.app_role
              else 'customer'::public.app_role
            end,
            coalesce(nullif(new.status, ''), 'active'),
            'customer',
            new.is_active,
            new.email_verified,
            new.nickname,
            new.nickname_completed,
            new.created_at,
            now(),
            new.last_login_at,
            new.last_login_at
          )
          on conflict (id) do update
            set email = excluded.email,
                full_name = excluded.full_name,
                role = excluded.role,
                status = excluded.status,
                source = 'customer',
                is_active = excluded.is_active,
                email_verified = excluded.email_verified,
                nickname = excluded.nickname,
                nickname_completed = excluded.nickname_completed,
                last_sign_in_at = excluded.last_sign_in_at,
                last_login_at = excluded.last_login_at,
                updated_at = now();
          return new;
        end;
        $$;

        revoke all on function public.sync_customer_user_to_public()
          from public, anon, authenticated;

        drop trigger if exists customer_users_sync_public on customer.users;
        create trigger customer_users_sync_public
          after insert or update or delete on customer.users
          for each row execute function public.sync_customer_user_to_public();
        """
    )

    # 7) Re-sync Auth profiles now that columns exist.
    op.execute(
        """
        insert into public.users (
          id, email, full_name, role, status, source,
          is_active, email_verified, created_at, updated_at,
          last_sign_in_at, last_login_at
        )
        select
          profiles.id,
          profiles.email,
          coalesce(profiles.full_name, ''),
          profiles.role,
          case
            when profiles.is_active = false then 'disabled'
            when profiles.email_verified = false then 'pending_verification'
            else 'active'
          end,
          'auth',
          profiles.is_active,
          profiles.email_verified,
          profiles.created_at,
          now(),
          auth_users.last_sign_in_at,
          profiles.last_login_at
        from public.profiles as profiles
        join auth.users as auth_users on auth_users.id = profiles.id
        on conflict (id) do update
          set email = excluded.email,
              full_name = excluded.full_name,
              role = excluded.role,
              status = excluded.status,
              source = 'auth',
              is_active = excluded.is_active,
              email_verified = excluded.email_verified,
              last_sign_in_at = excluded.last_sign_in_at,
              last_login_at = excluded.last_login_at,
              updated_at = now();
        """
    )


def downgrade():
    op.execute("drop trigger if exists customer_users_sync_public on customer.users")
    op.execute("drop function if exists public.sync_customer_user_to_public()")
    op.execute("delete from public.users where source = 'customer'")
    op.execute("alter table public.users drop column if exists nickname_completed")
    op.execute("alter table public.users drop column if exists nickname")
    op.execute("alter table public.users drop column if exists last_login_at")
    op.execute("alter table public.users drop column if exists source")
    op.execute("alter table public.users drop column if exists status")
    # Recreate Auth FK only for remaining auth-backed ids.
    op.execute(
        """
        delete from public.users u
        where not exists (select 1 from auth.users a where a.id = u.id);

        alter table public.users
          drop constraint if exists users_id_fkey;

        alter table public.users
          add constraint users_id_fkey
          foreign key (id) references auth.users (id) on delete cascade;
        """
    )
    op.execute(
        """
        create or replace view public.users_directory
        with (security_invoker = true)
        as
        select
          id::text as id, email, full_name, role::text as role,
          'active'::text as status, is_active, email_verified,
          created_at, updated_at, last_sign_in_at as last_login_at,
          'auth'::text as source
        from public.users;

        revoke all on public.users_directory from public, anon, authenticated;
        """
    )
