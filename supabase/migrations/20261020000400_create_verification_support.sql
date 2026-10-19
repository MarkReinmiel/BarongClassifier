-- Verification secrets stay out of the Data API. Only service_role can execute these functions.

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

-- PostgREST exposes the public schema. These wrappers reject every caller except service_role.
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
