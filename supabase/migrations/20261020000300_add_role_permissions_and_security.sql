-- Role checks and profile locks. Authorization reads profiles, not user metadata.

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
