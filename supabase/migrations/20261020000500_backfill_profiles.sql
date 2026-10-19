-- Auth users created before the profile trigger have no public.profiles row.
-- The table editor then shows an empty profiles table.

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
