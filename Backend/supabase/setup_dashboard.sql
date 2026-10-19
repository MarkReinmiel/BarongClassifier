-- Run in the NEW project SQL Editor:
-- https://supabase.com/dashboard/project/kmowqcadgtfpfxlxnkph/sql/new
--
-- Matches the trained CNN classes and dashboard overview cards.

-- ---------- profiles ----------
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text,
  full_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "Users can read own profile" on public.profiles;
create policy "Users can read own profile"
  on public.profiles for select to authenticated
  using (auth.uid() = id);

drop policy if exists "Users can insert own profile" on public.profiles;
create policy "Users can insert own profile"
  on public.profiles for insert to authenticated
  with check (auth.uid() = id);

drop policy if exists "Users can update own profile" on public.profiles;
create policy "Users can update own profile"
  on public.profiles for update to authenticated
  using (auth.uid() = id)
  with check (auth.uid() = id);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, full_name)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'full_name', '')
  )
  on conflict (id) do update
    set email = excluded.email,
        full_name = excluded.full_name,
        updated_at = now();
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------- textile types (CNN classes) ----------
create table if not exists public.textile_types (
  id serial primary key,
  slug text not null unique,
  display_name text not null,
  description text,
  created_at timestamptz not null default now()
);

insert into public.textile_types (slug, display_name, description)
values
  ('cocoon', 'Cocoon', 'Cocoon silk textile used in Barong Tagalog garments'),
  ('jusi', 'Jusi', 'Jusi textile used in Barong Tagalog garments'),
  ('pina', 'Piña', 'Piña textile used in Barong Tagalog garments')
on conflict (slug) do update
  set display_name = excluded.display_name,
      description = excluded.description;

alter table public.textile_types enable row level security;

drop policy if exists "Authenticated users can read textile types" on public.textile_types;
create policy "Authenticated users can read textile types"
  on public.textile_types for select to authenticated
  using (true);

-- ---------- model metrics (from training artifacts) ----------
create table if not exists public.model_metrics (
  id serial primary key,
  model_name text not null,
  test_accuracy numeric(5,4) not null,
  test_images integer not null,
  class_count integer not null,
  updated_at timestamptz not null default now()
);

delete from public.model_metrics;
insert into public.model_metrics (model_name, test_accuracy, test_images, class_count)
values ('MobileNetV2', 1.0000, 39, 3);

alter table public.model_metrics enable row level security;

drop policy if exists "Authenticated users can read model metrics" on public.model_metrics;
create policy "Authenticated users can read model metrics"
  on public.model_metrics for select to authenticated
  using (true);

-- ---------- classification history ----------
create table if not exists public.classifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  file_name text,
  predicted_label text not null,
  display_name text not null,
  confidence numeric(6,5) not null,
  image_path text,
  created_at timestamptz not null default now()
);

create index if not exists classifications_user_id_idx
  on public.classifications (user_id, created_at desc);

alter table public.classifications enable row level security;

drop policy if exists "Users can read own classifications" on public.classifications;
create policy "Users can read own classifications"
  on public.classifications for select to authenticated
  using (auth.uid() = user_id);

drop policy if exists "Users can insert own classifications" on public.classifications;
create policy "Users can insert own classifications"
  on public.classifications for insert to authenticated
  with check (auth.uid() = user_id);

-- ---------- dashboard functions ----------
create or replace function public.count_textile_types()
returns integer
language sql
stable
security invoker
set search_path = public
as $$
  select count(*)::integer from public.textile_types;
$$;

create or replace function public.get_model_accuracy_percent()
returns numeric
language sql
stable
security invoker
set search_path = public
as $$
  select round((test_accuracy * 100)::numeric, 0)
  from public.model_metrics
  order by id desc
  limit 1;
$$;

create or replace function public.count_user_classifications(
  p_user_id uuid default auth.uid()
)
returns integer
language sql
stable
security invoker
set search_path = public
as $$
  select count(*)::integer
  from public.classifications
  where user_id = coalesce(p_user_id, auth.uid());
$$;

create or replace function public.get_dashboard_overview()
returns json
language plpgsql
stable
security invoker
set search_path = public
as $$
declare
  result json;
begin
  select json_build_object(
    'textile_types', (select public.count_textile_types()),
    'model_accuracy', (select public.get_model_accuracy_percent()),
    'images_classified', (select public.count_user_classifications(auth.uid()))
  )
  into result;

  return result;
end;
$$;

grant execute on function public.count_textile_types() to authenticated;
grant execute on function public.get_model_accuracy_percent() to authenticated;
grant execute on function public.count_user_classifications(uuid) to authenticated;
grant execute on function public.get_dashboard_overview() to authenticated;
