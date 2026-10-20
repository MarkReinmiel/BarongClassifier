-- BarongClassifier Customer portal — latest SQL for the DB in Customer/.env
-- Head revision: 20261020_0006
--
-- public.users                 = account directory (Auth + Flask; no profiles table)
-- public.email_verifications   = mirror of customer OTP rows (no code_hash)
-- public.trusted_devices       = mirror of customer devices (no token_hash)
-- customer.*                   = Flask source of truth (includes secret hashes)

create schema if not exists customer;

create table if not exists customer.users (
  id varchar(36) primary key,
  email varchar(255) not null,
  password_hash varchar(255) not null,
  full_name varchar(120) not null default '',
  role varchar(32) not null default 'customer',
  status varchar(32) not null default 'pending_verification',
  email_verified boolean not null default false,
  nickname varchar(40),
  nickname_completed boolean not null default false,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_login_at timestamptz
);

create unique index if not exists ix_customer_users_email on customer.users (email);

create table if not exists customer.email_verifications (
  id varchar(36) primary key,
  user_id varchar(36) not null references customer.users (id) on delete cascade,
  purpose varchar(32) not null,
  code_hash varchar(128) not null,
  role varchar(32) not null default 'customer',
  status varchar(32) not null default 'pending',
  expires_at timestamptz not null,
  resend_available_at timestamptz not null,
  attempts integer not null default 0,
  locked_until timestamptz,
  consumed_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists customer.trusted_devices (
  id varchar(36) primary key,
  user_id varchar(36) not null references customer.users (id) on delete cascade,
  token_hash varchar(128) not null,
  label varchar(120),
  role varchar(32) not null default 'customer',
  status varchar(32) not null default 'active',
  created_at timestamptz not null default now(),
  last_used_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz
);

create table if not exists customer.classifications (
  id varchar(36) primary key,
  user_id varchar(36) not null references customer.users (id) on delete cascade,
  predicted_label varchar(64) not null,
  confidence double precision not null,
  image_name varchar(255),
  image_path varchar(512),
  role varchar(32) not null default 'customer',
  status varchar(32) not null default 'completed',
  created_at timestamptz not null default now()
);

create table if not exists public.users (
  id uuid primary key,
  email text,
  full_name text not null default '',
  role public.app_role not null default 'customer',
  status text not null default 'active',
  source text not null default 'auth',
  is_active boolean not null default true,
  email_verified boolean not null default false,
  must_change_password boolean not null default false,
  nickname text,
  nickname_completed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_sign_in_at timestamptz,
  last_login_at timestamptz
);

create table if not exists public.email_verifications (
  id uuid primary key,
  user_id uuid not null references public.users (id) on delete cascade,
  purpose text not null,
  role text not null default 'customer',
  status text not null default 'pending',
  expires_at timestamptz not null,
  resend_available_at timestamptz not null,
  attempts integer not null default 0,
  locked_until timestamptz,
  consumed_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.trusted_devices (
  id uuid primary key,
  user_id uuid not null references public.users (id) on delete cascade,
  label text,
  role text not null default 'customer',
  status text not null default 'active',
  created_at timestamptz not null default now(),
  last_used_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz
);

create table if not exists customer.alembic_version (
  version_num varchar(32) not null primary key
);

insert into customer.alembic_version (version_num)
values ('20261020_0006')
on conflict (version_num) do nothing;
