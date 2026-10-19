-- Paste this whole file into Supabase Dashboard → SQL Editor → Run.
-- It matches supabase/migrations and is safe to run more than once.
-- This file is not inside supabase/migrations, so "supabase db push" will not apply it again.

-- ---------- 1. profiles ----------

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

-- ---------- 2. classifications ----------

alter table public.classifications
  add column if not exists predicted_textile_type text,
  add column if not exists confidence_score numeric(6,5),
  add column if not exists image_reference text,
  add column if not exists image_path text;

update public.classifications
set
  predicted_textile_type = coalesce(predicted_textile_type, predicted_label),
  confidence_score = coalesce(confidence_score, confidence),
  image_reference = coalesce(image_reference, image_path);

create or replace function public.sync_classification_aliases()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.predicted_textile_type is null then
    new.predicted_textile_type := new.predicted_label;
  end if;
  if new.predicted_label is null then
    new.predicted_label := new.predicted_textile_type;
  end if;
  if new.confidence_score is null then
    new.confidence_score := new.confidence;
  end if;
  if new.confidence is null then
    new.confidence := new.confidence_score;
  end if;
  if new.image_reference is null then
    new.image_reference := new.image_path;
  end if;
  if new.image_path is null then
    new.image_path := new.image_reference;
  end if;
  return new;
end;
$$;

drop trigger if exists classifications_sync_aliases on public.classifications;
create trigger classifications_sync_aliases
  before insert or update on public.classifications
  for each row execute function public.sync_classification_aliases();

-- ---------- 3. roles and row security ----------

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.profiles
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
    select 1
    from public.profiles
    where id = auth.uid()
      and is_active
      and email_verified
  );
$$;

revoke all on function public.is_admin() from public, anon;
revoke all on function public.is_account_current() from public, anon;
grant execute on function public.is_admin() to authenticated, service_role;
grant execute on function public.is_account_current() to authenticated, service_role;

create or replace function public.protect_profile_privileges()
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
    from public.profiles
    where role = 'admin'
      and is_active
      and id <> old.id;
    if other_active_admins < 1 then
      raise exception 'Cannot remove the last active administrator';
    end if;
  end if;

  if actor_is_service then
    return new;
  end if;

  select p.role into actor_role
  from public.profiles p
  where p.id = auth.uid();

  if actor_role = 'admin' and auth.uid() is distinct from old.id then
    return new;
  end if;

  new.role := old.role;
  new.is_active := old.is_active;
  new.email_verified := old.email_verified;
  new.must_change_password := old.must_change_password;
  new.last_login_at := old.last_login_at;
  new.email := old.email;
  return new;
end;
$$;

drop trigger if exists profiles_protect_privileges on public.profiles;
create trigger profiles_protect_privileges
  before insert or update on public.profiles
  for each row execute function public.protect_profile_privileges();

revoke all on function public.protect_profile_privileges() from public, anon, authenticated;

drop policy if exists "Users can read own profile" on public.profiles;
create policy "Users can read own profile"
  on public.profiles for select to authenticated
  using (auth.uid() = id or public.is_admin());

drop policy if exists "Users can insert own profile" on public.profiles;
create policy "Users can insert own profile"
  on public.profiles for insert to authenticated
  with check (auth.uid() = id);

drop policy if exists "Users can update own profile" on public.profiles;
create policy "Users can update own profile"
  on public.profiles for update to authenticated
  using (auth.uid() = id or public.is_admin())
  with check (auth.uid() = id or public.is_admin());

drop policy if exists "Users can read own classifications" on public.classifications;
create policy "Users can read own classifications"
  on public.classifications for select to authenticated
  using (auth.uid() = user_id and public.is_account_current());

drop policy if exists "Admins can read classifications" on public.classifications;
create policy "Admins can read classifications"
  on public.classifications for select to authenticated
  using (public.is_admin());

drop policy if exists "Users can insert own classifications" on public.classifications;
create policy "Users can insert own classifications"
  on public.classifications for insert to authenticated
  with check (auth.uid() = user_id and public.is_account_current());

-- ---------- 4. email verification ----------

create schema if not exists private;

revoke all on schema private from public, anon, authenticated;
grant usage on schema private to service_role;

create table if not exists private.email_verifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  code_hash text not null,
  expires_at timestamptz not null,
  resend_available_at timestamptz not null,
  attempts integer not null default 0,
  consumed_at timestamptz,
  locked_until timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists email_verifications_user_idx
  on private.email_verifications (user_id, created_at desc);

create table if not exists private.verification_challenges (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  token_hash text not null unique,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

alter table private.email_verifications enable row level security;
alter table private.verification_challenges enable row level security;

revoke all on private.email_verifications from public, anon, authenticated;
revoke all on private.verification_challenges from public, anon, authenticated;
grant select, insert, update, delete on private.email_verifications to service_role;
grant select, insert, update, delete on private.verification_challenges to service_role;

create or replace function private.issue_verification_code(
  p_user_id uuid,
  p_code_hash text
)
returns jsonb
language plpgsql
security definer
set search_path = private, public
as $$
declare
  latest private.email_verifications%rowtype;
  now_ts timestamptz := clock_timestamp();
  expires_at timestamptz;
  resend_at timestamptz;
  new_id uuid;
begin
  select * into latest
  from private.email_verifications
  where user_id = p_user_id
    and consumed_at is null
  order by created_at desc
  limit 1
  for update;

  if latest.id is not null and latest.locked_until is not null and latest.locked_until > now_ts then
    return jsonb_build_object(
      'ok', false,
      'error', 'locked',
      'retry_after_seconds', ceil(extract(epoch from (latest.locked_until - now_ts)))
    );
  end if;

  if latest.id is not null and latest.resend_available_at > now_ts and latest.expires_at > now_ts then
    return jsonb_build_object(
      'ok', false,
      'error', 'cooldown',
      'retry_after_seconds', ceil(extract(epoch from (latest.resend_available_at - now_ts)))
    );
  end if;

  update private.email_verifications
  set consumed_at = now_ts
  where user_id = p_user_id
    and consumed_at is null;

  expires_at := now_ts + interval '1 hour';
  resend_at := now_ts + interval '60 seconds';

  insert into private.email_verifications (
    user_id, code_hash, expires_at, resend_available_at
  )
  values (p_user_id, p_code_hash, expires_at, resend_at)
  returning id into new_id;

  return jsonb_build_object(
    'ok', true,
    'id', new_id,
    'expires_at', expires_at,
    'resend_available_at', resend_at
  );
end;
$$;

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
    return jsonb_build_object('ok', false, 'error', 'invalid');
  end if;

  if rec.locked_until is not null and rec.locked_until > now_ts then
    return jsonb_build_object('ok', false, 'error', 'locked');
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
    where id = rec.id
      and consumed_at is null;

    perform set_config('app.trusted_profile_write', '1', true);
    update public.profiles
    set email_verified = true,
        updated_at = now_ts
    where id = p_user_id;

    delete from private.verification_challenges
    where user_id = p_user_id;

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

create or replace function private.save_challenge(
  p_user_id uuid,
  p_token_hash text
)
returns void
language plpgsql
security definer
set search_path = private
as $$
begin
  delete from private.verification_challenges
  where user_id = p_user_id
     or expires_at <= clock_timestamp();

  insert into private.verification_challenges (user_id, token_hash, expires_at)
  values (p_user_id, p_token_hash, clock_timestamp() + interval '1 hour');
end;
$$;

create or replace function private.take_challenge(p_token_hash text)
returns uuid
language plpgsql
security definer
set search_path = private
as $$
declare
  found_user uuid;
begin
  select user_id into found_user
  from private.verification_challenges
  where token_hash = p_token_hash
    and expires_at > clock_timestamp()
  for update;

  return found_user;
end;
$$;

revoke all on function private.issue_verification_code(uuid, text) from public, anon, authenticated;
revoke all on function private.consume_verification_code(uuid, text) from public, anon, authenticated;
revoke all on function private.save_challenge(uuid, text) from public, anon, authenticated;
revoke all on function private.take_challenge(text) from public, anon, authenticated;
grant execute on function private.issue_verification_code(uuid, text) to service_role;
grant execute on function private.consume_verification_code(uuid, text) to service_role;
grant execute on function private.save_challenge(uuid, text) to service_role;
grant execute on function private.take_challenge(text) to service_role;

create or replace function public.svc_issue_verification_code(p_user_id uuid, p_code_hash text)
returns jsonb
language plpgsql
security definer
set search_path = private, public
as $$
begin
  if coalesce(auth.role(), '') is distinct from 'service_role' then
    raise exception 'forbidden';
  end if;
  return private.issue_verification_code(p_user_id, p_code_hash);
end;
$$;

create or replace function public.svc_consume_verification_code(p_user_id uuid, p_code_hash text)
returns jsonb
language plpgsql
security definer
set search_path = private, public
as $$
begin
  if coalesce(auth.role(), '') is distinct from 'service_role' then
    raise exception 'forbidden';
  end if;
  return private.consume_verification_code(p_user_id, p_code_hash);
end;
$$;

create or replace function public.svc_save_challenge(p_user_id uuid, p_token_hash text)
returns void
language plpgsql
security definer
set search_path = private, public
as $$
begin
  if coalesce(auth.role(), '') is distinct from 'service_role' then
    raise exception 'forbidden';
  end if;
  perform private.save_challenge(p_user_id, p_token_hash);
end;
$$;

create or replace function public.svc_take_challenge(p_token_hash text)
returns uuid
language plpgsql
security definer
set search_path = private, public
as $$
begin
  if coalesce(auth.role(), '') is distinct from 'service_role' then
    raise exception 'forbidden';
  end if;
  return private.take_challenge(p_token_hash);
end;
$$;

revoke all on function public.svc_issue_verification_code(uuid, text) from public, anon, authenticated;
revoke all on function public.svc_consume_verification_code(uuid, text) from public, anon, authenticated;
revoke all on function public.svc_save_challenge(uuid, text) from public, anon, authenticated;
revoke all on function public.svc_take_challenge(text) from public, anon, authenticated;
grant execute on function public.svc_issue_verification_code(uuid, text) to service_role;
grant execute on function public.svc_consume_verification_code(uuid, text) to service_role;
grant execute on function public.svc_save_challenge(uuid, text) to service_role;
grant execute on function public.svc_take_challenge(text) to service_role;

-- ---------- 5. copy Auth users into profiles ----------

do $$
begin
  perform set_config('app.trusted_profile_write', '1', true);

  insert into public.profiles (
    id,
    email,
    full_name,
    role,
    is_active,
    email_verified,
    must_change_password
  )
  select
    users.id,
    lower(trim(users.email)),
    coalesce(users.raw_user_meta_data ->> 'full_name', ''),
    case
      when lower(users.email) = 'barongclassifier@gmail.com' then 'admin'::public.app_role
      else 'customer'::public.app_role
    end,
    true,
    users.email_confirmed_at is not null,
    false
  from auth.users as users
  where not exists (
    select 1
    from public.profiles as profiles
    where profiles.id = users.id
  );
end $$;
