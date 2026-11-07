-- Incomplete customer signups stay here until email verification succeeds.
-- No customer.users / public.users row is created until the code is accepted.

create table if not exists customer.pending_signups (
  id text primary key,
  email text not null,
  password_hash text not null,
  code_hash text not null,
  status text not null default 'pending',
  expires_at timestamptz not null,
  resend_available_at timestamptz not null,
  attempts integer not null default 0,
  locked_until timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists ix_customer_pending_signups_email
  on customer.pending_signups (email);

alter table customer.pending_signups enable row level security;
