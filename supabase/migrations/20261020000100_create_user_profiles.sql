-- Extend the existing profiles table. Do not recreate it or touch passwords.

do $$
begin
  create type public.app_role as enum ('admin', 'owner', 'customer');
exception
  when duplicate_object then null;
end $$;

alter table public.profiles
  add column if not exists role public.app_role not null default 'customer',
  add column if not exists is_active boolean not null default true,
  add column if not exists email_verified boolean not null default false,
  add column if not exists last_login_at timestamptz,
  add column if not exists must_change_password boolean not null default false;

-- Accounts that already exist keep working. New rows default to unverified.
update public.profiles
set email_verified = true
where email_verified = false;

update public.profiles
set email = lower(trim(email))
where email is not null
  and email is distinct from lower(trim(email));

create unique index if not exists profiles_email_unique
  on public.profiles (email);

create index if not exists profiles_role_idx
  on public.profiles (role);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (
    id, email, full_name, role, is_active, email_verified, must_change_password
  )
  values (
    new.id,
    lower(trim(new.email)),
    coalesce(new.raw_user_meta_data ->> 'full_name', ''),
    'customer',
    true,
    false,
    false
  )
  on conflict (id) do update
    set email = excluded.email,
        full_name = excluded.full_name,
        updated_at = now();
  return new;
end;
$$;

revoke all on function public.handle_new_user() from public, anon, authenticated;
