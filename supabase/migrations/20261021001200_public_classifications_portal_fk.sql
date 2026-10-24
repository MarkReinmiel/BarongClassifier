-- Allow Flask Customer/Owner portal accounts to write public.classifications.
-- Previously user_id referenced auth.users only, so portal saves never appeared
-- in the Supabase Table Editor.

alter table public.classifications
  drop constraint if exists classifications_user_id_fkey;

comment on column public.classifications.user_id is
  'Portal (customer.users) or Auth user id. Flask apps write here for Table Editor visibility.';
