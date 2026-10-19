-- New Auth accounts can sign in immediately while email codes are turned off.

create or replace function public.confirm_auth_user()
returns trigger
language plpgsql
security definer
set search_path = auth, public
as $$
begin
  if new.email_confirmed_at is null then
    new.email_confirmed_at := now();
  end if;
  return new;
end;
$$;

drop trigger if exists confirm_auth_user on auth.users;
create trigger confirm_auth_user
  before insert on auth.users
  for each row execute function public.confirm_auth_user();

revoke all on function public.confirm_auth_user() from public, anon, authenticated;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  perform set_config('app.trusted_profile_write', '1', true);
  insert into public.profiles (
    id, email, full_name, role, is_active, email_verified, must_change_password
  )
  values (
    new.id,
    lower(trim(new.email)),
    coalesce(new.raw_user_meta_data ->> 'full_name', ''),
    'customer',
    true,
    true,
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
