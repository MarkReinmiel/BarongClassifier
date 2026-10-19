-- Public directory of accounts. Auth passwords stay in auth.users.

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

create unique index if not exists users_email_unique
  on public.users (email);

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
    id,
    email,
    full_name,
    role,
    is_active,
    email_verified,
    created_at,
    updated_at,
    last_sign_in_at
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

drop trigger if exists profiles_sync_users on public.profiles;
create trigger profiles_sync_users
  after insert or update on public.profiles
  for each row execute function public.sync_public_user();

revoke all on function public.sync_public_user() from public, anon, authenticated;

insert into public.users (
  id,
  email,
  full_name,
  role,
  is_active,
  email_verified,
  created_at,
  updated_at,
  last_sign_in_at
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

-- Existing accounts can sign in. New accounts still follow the verification setting.
update auth.users
set email_confirmed_at = coalesce(email_confirmed_at, now())
where email_confirmed_at is null;

do $$
begin
  perform set_config('app.trusted_profile_write', '1', true);
  update public.profiles
  set email_verified = true
  where email_verified = false;
end $$;
