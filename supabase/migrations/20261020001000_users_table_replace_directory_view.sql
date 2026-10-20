-- Replace public.users_directory VIEW with real rows in public.users.
-- Removes Security Definer / public-view API advisories permanently.
-- Passwords remain only in customer.users.password_hash.

drop view if exists public.users_directory cascade;
drop view if exists public.customer_portal_users cascade;
drop view if exists public.customer_portal_email_verifications cascade;
drop view if exists public.customer_portal_trusted_devices cascade;
drop view if exists public.customer_portal_classifications cascade;
drop view if exists public.portal_classifications cascade;
drop view if exists public.email_verifications cascade;
drop view if exists public.trusted_devices cascade;

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

revoke all on table public.users from anon;
grant select on table public.users to authenticated;
grant all on table public.users to service_role, postgres;

-- Merge Flask portal accounts into public.users (no password_hash).
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

create or replace function public.sync_customer_user_to_public()
returns trigger
language plpgsql
security definer
set search_path = public, customer
as $$
begin
  if tg_op = 'DELETE' then
    delete from public.users where id = old.id::uuid and source = 'customer';
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
