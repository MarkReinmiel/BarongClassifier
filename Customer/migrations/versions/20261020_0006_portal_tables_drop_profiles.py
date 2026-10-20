"""Public email_verifications + trusted_devices tables; drop profiles.

Revision ID: 20261020_0006
Revises: 20261020_0005
Create Date: 2026-10-20

- Add must_change_password on public.users (from profiles)
- Create public.email_verifications / trusted_devices (real tables, no secret hashes)
- Sync from customer.* via triggers
- Retarget Auth helpers to public.users
- Drop public.profiles
"""

from alembic import op

revision = "20261020_0006"
down_revision = "20261020_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        -- 1) Fold profiles fields into public.users
        alter table public.users
          add column if not exists must_change_password boolean not null default false;

        update public.users u
        set must_change_password = coalesce(p.must_change_password, false),
            full_name = coalesce(nullif(u.full_name, ''), p.full_name, u.full_name),
            role = coalesce(p.role, u.role),
            is_active = coalesce(p.is_active, u.is_active),
            email_verified = coalesce(p.email_verified, u.email_verified),
            last_login_at = coalesce(u.last_login_at, p.last_login_at),
            updated_at = now()
        from public.profiles p
        where p.id = u.id and u.source = 'auth';

        insert into public.users (
          id, email, full_name, role, status, source,
          is_active, email_verified, must_change_password,
          created_at, updated_at, last_login_at, last_sign_in_at
        )
        select
          p.id,
          p.email,
          coalesce(p.full_name, ''),
          p.role,
          case
            when p.is_active = false then 'disabled'
            when p.email_verified = false then 'pending_verification'
            else 'active'
          end,
          'auth',
          p.is_active,
          p.email_verified,
          coalesce(p.must_change_password, false),
          p.created_at,
          now(),
          p.last_login_at,
          p.last_login_at
        from public.profiles p
        where not exists (select 1 from public.users u where u.id = p.id)
        on conflict (id) do nothing;
        """
    )

    op.execute(
        """
        -- 2) Portal tables in public (no code_hash / token_hash — secrets stay in customer.*)
        create table if not exists public.email_verifications (
          id uuid primary key,
          user_id uuid not null references public.users (id) on delete cascade,
          purpose text not null,
          role text not null default 'customer',
          status text not null default 'pending',
          expires_at timestamptz not null,
          resend_available_at timestamptz not null,
          attempts integer not null default 0,
          locked_until timestamptz,
          consumed_at timestamptz,
          created_at timestamptz not null default now()
        );

        create index if not exists email_verifications_user_idx
          on public.email_verifications (user_id, created_at desc);

        create table if not exists public.trusted_devices (
          id uuid primary key,
          user_id uuid not null references public.users (id) on delete cascade,
          label text,
          role text not null default 'customer',
          status text not null default 'active',
          created_at timestamptz not null default now(),
          last_used_at timestamptz not null default now(),
          expires_at timestamptz not null,
          revoked_at timestamptz
        );

        create index if not exists trusted_devices_user_idx
          on public.trusted_devices (user_id);

        alter table public.email_verifications enable row level security;
        alter table public.trusted_devices enable row level security;

        revoke all on table public.email_verifications from public, anon, authenticated;
        revoke all on table public.trusted_devices from public, anon, authenticated;
        grant all on table public.email_verifications to postgres, service_role;
        grant all on table public.trusted_devices to postgres, service_role;

        -- Backfill from customer schema
        insert into public.email_verifications (
          id, user_id, purpose, role, status, expires_at, resend_available_at,
          attempts, locked_until, consumed_at, created_at
        )
        select
          e.id::uuid,
          e.user_id::uuid,
          e.purpose,
          coalesce(e.role, 'customer'),
          coalesce(e.status, 'pending'),
          e.expires_at,
          e.resend_available_at,
          e.attempts,
          e.locked_until,
          e.consumed_at,
          e.created_at
        from customer.email_verifications e
        where exists (select 1 from public.users u where u.id = e.user_id::uuid)
        on conflict (id) do update
          set purpose = excluded.purpose,
              role = excluded.role,
              status = excluded.status,
              expires_at = excluded.expires_at,
              resend_available_at = excluded.resend_available_at,
              attempts = excluded.attempts,
              locked_until = excluded.locked_until,
              consumed_at = excluded.consumed_at;

        insert into public.trusted_devices (
          id, user_id, label, role, status, created_at, last_used_at, expires_at, revoked_at
        )
        select
          d.id::uuid,
          d.user_id::uuid,
          d.label,
          coalesce(d.role, 'customer'),
          coalesce(d.status, 'active'),
          d.created_at,
          d.last_used_at,
          d.expires_at,
          d.revoked_at
        from customer.trusted_devices d
        where exists (select 1 from public.users u where u.id = d.user_id::uuid)
        on conflict (id) do update
          set label = excluded.label,
              role = excluded.role,
              status = excluded.status,
              last_used_at = excluded.last_used_at,
              expires_at = excluded.expires_at,
              revoked_at = excluded.revoked_at;
        """
    )

    op.execute(
        """
        -- 3) Sync triggers from customer.* → public.* (no secrets)
        create or replace function public.sync_customer_email_verification()
        returns trigger
        language plpgsql
        security definer
        set search_path = public, customer
        as $$
        begin
          if tg_op = 'DELETE' then
            delete from public.email_verifications where id = old.id::uuid;
            return old;
          end if;
          if not exists (select 1 from public.users where id = new.user_id::uuid) then
            return new;
          end if;
          insert into public.email_verifications (
            id, user_id, purpose, role, status, expires_at, resend_available_at,
            attempts, locked_until, consumed_at, created_at
          ) values (
            new.id::uuid, new.user_id::uuid, new.purpose,
            coalesce(new.role, 'customer'), coalesce(new.status, 'pending'),
            new.expires_at, new.resend_available_at, new.attempts,
            new.locked_until, new.consumed_at, new.created_at
          )
          on conflict (id) do update set
            purpose = excluded.purpose,
            role = excluded.role,
            status = excluded.status,
            expires_at = excluded.expires_at,
            resend_available_at = excluded.resend_available_at,
            attempts = excluded.attempts,
            locked_until = excluded.locked_until,
            consumed_at = excluded.consumed_at;
          return new;
        end;
        $$;

        create or replace function public.sync_customer_trusted_device()
        returns trigger
        language plpgsql
        security definer
        set search_path = public, customer
        as $$
        begin
          if tg_op = 'DELETE' then
            delete from public.trusted_devices where id = old.id::uuid;
            return old;
          end if;
          if not exists (select 1 from public.users where id = new.user_id::uuid) then
            return new;
          end if;
          insert into public.trusted_devices (
            id, user_id, label, role, status, created_at, last_used_at, expires_at, revoked_at
          ) values (
            new.id::uuid, new.user_id::uuid, new.label,
            coalesce(new.role, 'customer'), coalesce(new.status, 'active'),
            new.created_at, new.last_used_at, new.expires_at, new.revoked_at
          )
          on conflict (id) do update set
            label = excluded.label,
            role = excluded.role,
            status = excluded.status,
            last_used_at = excluded.last_used_at,
            expires_at = excluded.expires_at,
            revoked_at = excluded.revoked_at;
          return new;
        end;
        $$;

        revoke all on function public.sync_customer_email_verification()
          from public, anon, authenticated;
        revoke all on function public.sync_customer_trusted_device()
          from public, anon, authenticated;

        drop trigger if exists customer_email_verifications_sync_public
          on customer.email_verifications;
        create trigger customer_email_verifications_sync_public
          after insert or update or delete on customer.email_verifications
          for each row execute function public.sync_customer_email_verification();

        drop trigger if exists customer_trusted_devices_sync_public
          on customer.trusted_devices;
        create trigger customer_trusted_devices_sync_public
          after insert or update or delete on customer.trusted_devices
          for each row execute function public.sync_customer_trusted_device();
        """
    )

    op.execute(
        """
        -- 4) Auth helpers → public.users (replace profiles)
        create or replace function public.is_admin()
        returns boolean
        language sql
        stable
        security definer
        set search_path = public
        as $$
          select exists (
            select 1 from public.users
            where id = auth.uid()
              and role = 'admin'
              and is_active
              and email_verified
          );
        $$;

        create or replace function public.is_account_current()
        returns boolean
        language sql
        stable
        security definer
        set search_path = public
        as $$
          select exists (
            select 1 from public.users
            where id = auth.uid()
              and is_active
              and email_verified
          );
        $$;

        create or replace function public.handle_new_user()
        returns trigger
        language plpgsql
        security definer
        set search_path = public
        as $$
        begin
          insert into public.users (
            id, email, full_name, role, status, source,
            is_active, email_verified, must_change_password,
            created_at, updated_at
          )
          values (
            new.id,
            lower(trim(new.email)),
            coalesce(new.raw_user_meta_data ->> 'full_name', ''),
            'customer',
            'pending_verification',
            'auth',
            true,
            false,
            false,
            now(),
            now()
          )
          on conflict (id) do update
            set email = excluded.email,
                full_name = excluded.full_name,
                updated_at = now();
          return new;
        end;
        $$;

        create or replace function public.protect_user_privileges()
        returns trigger
        language plpgsql
        security definer
        set search_path = public
        as $$
        declare
          actor_role public.app_role;
          actor_is_service boolean;
          other_active_admins integer;
        begin
          if new.email is not null then
            new.email := nullif(lower(trim(new.email)), '');
          end if;

          actor_is_service := coalesce(auth.role(), '') = 'service_role'
            or current_setting('app.trusted_profile_write', true) = '1';

          if tg_op = 'INSERT' then
            if not actor_is_service then
              new.role := 'customer';
              new.is_active := true;
              new.email_verified := false;
              new.must_change_password := false;
              new.source := coalesce(new.source, 'auth');
              new.status := coalesce(new.status, 'pending_verification');
            end if;
            if new.role is null then
              new.role := 'customer';
            end if;
            return new;
          end if;

          if old.role = 'admin'
             and old.is_active
             and (new.role is distinct from 'admin' or new.is_active is distinct from true) then
            select count(*) into other_active_admins
            from public.users
            where role = 'admin' and is_active and id <> old.id;
            if other_active_admins < 1 then
              raise exception 'Cannot remove the last active administrator';
            end if;
          end if;

          if actor_is_service then
            return new;
          end if;

          select u.role into actor_role from public.users u where u.id = auth.uid();

          if actor_role = 'admin' and auth.uid() is distinct from old.id then
            return new;
          end if;

          new.role := old.role;
          new.is_active := old.is_active;
          new.email_verified := old.email_verified;
          new.must_change_password := old.must_change_password;
          new.last_login_at := old.last_login_at;
          new.source := old.source;
          new.email := old.email;
          return new;
        end;
        $$;

        revoke all on function public.protect_user_privileges() from public, anon, authenticated;

        drop trigger if exists users_protect_privileges on public.users;
        create trigger users_protect_privileges
          before insert or update on public.users
          for each row execute function public.protect_user_privileges();

        -- Auth signup already inserts users via handle_new_user; drop profiles sync.
        drop trigger if exists profiles_sync_users on public.profiles;
        drop trigger if exists profiles_protect_privileges on public.profiles;

        drop policy if exists "Users can read own user row" on public.users;
        create policy "Users can read own user row"
          on public.users for select to authenticated
          using (
            (source = 'auth' and auth.uid() = id)
            or public.is_admin()
          );

        drop policy if exists "Users can update own user row" on public.users;
        create policy "Users can update own user row"
          on public.users for update to authenticated
          using (
            (source = 'auth' and auth.uid() = id)
            or public.is_admin()
          )
          with check (
            (source = 'auth' and auth.uid() = id)
            or public.is_admin()
          );

        -- Verification RPC: mark users verified instead of profiles
        create or replace function private.consume_verification_code(
          p_user_id uuid,
          p_code_hash text
        )
        returns jsonb
        language plpgsql
        security definer
        set search_path = private, public
        as $$
        declare
          rec private.email_verifications%rowtype;
          now_ts timestamptz := clock_timestamp();
          next_attempts integer;
        begin
          select * into rec
          from private.email_verifications
          where user_id = p_user_id
            and consumed_at is null
          order by created_at desc
          limit 1
          for update;

          if rec.id is null then
            return jsonb_build_object('ok', false, 'error', 'missing');
          end if;

          if rec.locked_until is not null and rec.locked_until > now_ts then
            return jsonb_build_object(
              'ok', false,
              'error', 'locked',
              'retry_after_seconds', ceil(extract(epoch from (rec.locked_until - now_ts)))
            );
          end if;

          if rec.expires_at <= now_ts then
            return jsonb_build_object('ok', false, 'error', 'expired');
          end if;

          if rec.attempts >= 5 then
            update private.email_verifications
            set locked_until = now_ts + interval '15 minutes'
            where id = rec.id;
            return jsonb_build_object('ok', false, 'error', 'locked');
          end if;

          if rec.code_hash = p_code_hash then
            update private.email_verifications
            set consumed_at = now_ts
            where id = rec.id and consumed_at is null;

            perform set_config('app.trusted_profile_write', '1', true);
            update public.users
            set email_verified = true,
                status = 'active',
                updated_at = now_ts
            where id = p_user_id;

            delete from private.verification_challenges where user_id = p_user_id;
            return jsonb_build_object('ok', true);
          end if;

          next_attempts := rec.attempts + 1;
          update private.email_verifications
          set attempts = next_attempts,
              locked_until = case
                when next_attempts >= 5 then now_ts + interval '15 minutes'
                else locked_until
              end
          where id = rec.id;

          if next_attempts >= 5 then
            return jsonb_build_object('ok', false, 'error', 'locked');
          end if;
          return jsonb_build_object('ok', false, 'error', 'invalid');
        end;
        $$;
        """
    )

    # 5) Drop profiles (data already in public.users)
    op.execute("drop trigger if exists profiles_sync_users on public.profiles")
    op.execute("drop trigger if exists profiles_protect_privileges on public.profiles")
    op.execute("drop table if exists public.profiles cascade")


def downgrade():
    op.execute(
        """
        create table if not exists public.profiles (
          id uuid primary key references auth.users (id) on delete cascade,
          email text,
          full_name text,
          created_at timestamptz default now(),
          updated_at timestamptz default now(),
          role public.app_role not null default 'customer',
          is_active boolean not null default true,
          email_verified boolean not null default false,
          last_login_at timestamptz,
          must_change_password boolean not null default false
        );

        insert into public.profiles (
          id, email, full_name, role, is_active, email_verified,
          must_change_password, created_at, updated_at, last_login_at
        )
        select
          id, email, full_name, role, is_active, email_verified,
          must_change_password, created_at, updated_at, last_login_at
        from public.users
        where source = 'auth'
        on conflict (id) do nothing;
        """
    )
    op.execute("drop trigger if exists customer_email_verifications_sync_public on customer.email_verifications")
    op.execute("drop trigger if exists customer_trusted_devices_sync_public on customer.trusted_devices")
    op.execute("drop function if exists public.sync_customer_email_verification()")
    op.execute("drop function if exists public.sync_customer_trusted_device()")
    op.execute("drop table if exists public.trusted_devices cascade")
    op.execute("drop table if exists public.email_verifications cascade")
