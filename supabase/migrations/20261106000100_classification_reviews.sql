-- Owner dataset review for customer classifications.
-- Does not alter classification history rows; review lives alongside them.

create table if not exists public.classification_reviews (
  id uuid primary key default gen_random_uuid(),
  classification_id uuid not null unique,
  customer_user_id text,
  image_url text,
  predicted_label text,
  predicted_confidence double precision,
  verified_label text,
  review_status text not null default 'pending_review'
    check (review_status in (
      'pending_review',
      'approved',
      'rejected',
      'uncertain',
      'added_to_dataset'
    )),
  rejection_reason text,
  reviewed_by text,
  reviewed_at timestamptz,
  notes text,
  dataset_version text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists classification_reviews_status_idx
  on public.classification_reviews (review_status);

create index if not exists classification_reviews_reviewed_at_idx
  on public.classification_reviews (reviewed_at desc nulls last);

create table if not exists public.classification_review_events (
  id uuid primary key default gen_random_uuid(),
  classification_id uuid not null,
  review_id uuid references public.classification_reviews(id) on delete cascade,
  action text not null,
  previous_status text,
  new_status text not null,
  verified_label text,
  rejection_reason text,
  actor_user_id text,
  created_at timestamptz not null default now()
);

create index if not exists classification_review_events_class_idx
  on public.classification_review_events (classification_id, created_at desc);

-- Soft FK: classifications.user_id is text/uuid portal id; avoid hard auth.users FK.
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'classification_reviews_classification_id_fkey'
  ) then
    alter table public.classification_reviews
      add constraint classification_reviews_classification_id_fkey
      foreign key (classification_id)
      references public.classifications(id)
      on delete cascade;
  end if;
exception
  when others then
    -- Keep table usable even if classifications PK type differs slightly.
    raise notice 'classification_reviews FK skipped: %', sqlerrm;
end $$;

comment on table public.classification_reviews is
  'Owner decisions for including customer classification images in future training datasets.';
comment on table public.classification_review_events is
  'Audit trail of Owner approve / reject / uncertain / added_to_dataset actions.';
