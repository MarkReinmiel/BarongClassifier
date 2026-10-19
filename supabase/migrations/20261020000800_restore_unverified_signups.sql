-- New accounts stay unverified until the backend accepts the emailed code.
-- Supabase Auth can still confirm the login email so the password check works.
-- Existing verified profiles are left unchanged.

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
