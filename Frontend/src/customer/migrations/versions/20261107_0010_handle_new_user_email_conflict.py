"""Allow Auth/Google signup when email already exists in public.users.

Revision ID: 20261107_0010
Revises: 20261107_0009
Create Date: 2026-11-07

handle_new_user previously only ON CONFLICT (id). Password signups insert a
Flask-owned public.users row first; Google Auth then creates auth.users with a
new id and the same email, which hit users_email_unique and surfaced as
\"Database error saving new user\". Skip the insert when the email is already
present so OAuth can finish and Flask can sign the existing portal user in.
"""

from alembic import op

revision = "20261107_0010"
down_revision = "20261107_0009"
branch_labels = None
depends_on = None


UP_SQL = """
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if exists (
    select 1
    from public.users
    where lower(trim(email)) = lower(trim(new.email))
  ) then
    update public.users
    set
      updated_at = now(),
      email_verified = case
        when new.email_confirmed_at is not null then true
        else email_verified
      end,
      full_name = case
        when coalesce(nullif(trim(full_name), ''), '') = ''
          then coalesce(new.raw_user_meta_data ->> 'full_name', full_name)
        else full_name
      end
    where lower(trim(email)) = lower(trim(new.email));
    return new;
  end if;

  insert into public.users (
    id, email, full_name, role, status, source,
    is_active, email_verified, must_change_password,
    created_at, updated_at
  )
  values (
    new.id,
    lower(trim(new.email)),
    coalesce(new.raw_user_meta_data ->> 'full_name', ''),
    'customer',
    'pending_verification',
    'auth',
    true,
    false,
    false,
    now(),
    now()
  )
  on conflict (id) do update
    set email = excluded.email,
        full_name = excluded.full_name,
        updated_at = now();
  return new;
end;
$$;
"""

DOWN_SQL = """
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.users (
    id, email, full_name, role, status, source,
    is_active, email_verified, must_change_password,
    created_at, updated_at
  )
  values (
    new.id,
    lower(trim(new.email)),
    coalesce(new.raw_user_meta_data ->> 'full_name', ''),
    'customer',
    'pending_verification',
    'auth',
    true,
    false,
    false,
    now(),
    now()
  )
  on conflict (id) do update
    set email = excluded.email,
        full_name = excluded.full_name,
        updated_at = now();
  return new;
end;
$$;
"""


def upgrade() -> None:
    op.execute(UP_SQL)


def downgrade() -> None:
    op.execute(DOWN_SQL)
