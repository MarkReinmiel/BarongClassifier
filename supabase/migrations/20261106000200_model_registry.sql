-- Model registry for zero-downtime candidate training + controlled deployment.
-- Production inference keeps using app model files until Owner deploys a candidate.

create table if not exists public.model_versions (
  id uuid primary key default gen_random_uuid(),
  version_label text not null unique,
  version_number integer not null unique,
  status text not null default 'training'
    check (status in (
      'active',
      'training',
      'pending_evaluation',
      'evaluation_passed',
      'evaluation_failed',
      'approved_for_deployment',
      'deployed',
      'rejected',
      'archived',
      'failed'
    )),
  artifact_dir text,
  model_filename text default 'main_classifier.keras',
  labels_filename text default 'labels.json',
  metrics_json jsonb not null default '{}'::jsonb,
  dataset_summary jsonb not null default '{}'::jsonb,
  parent_version_id uuid references public.model_versions(id) on delete set null,
  is_production boolean not null default false,
  created_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deployed_at timestamptz,
  notes text
);

create index if not exists model_versions_status_idx
  on public.model_versions (status);
create index if not exists model_versions_production_idx
  on public.model_versions (is_production);

create table if not exists public.training_jobs (
  id uuid primary key default gen_random_uuid(),
  model_version_id uuid not null references public.model_versions(id) on delete cascade,
  status text not null default 'queued'
    check (status in (
      'queued',
      'running',
      'succeeded',
      'failed',
      'cancelled'
    )),
  attempt integer not null default 1,
  progress_pct double precision not null default 0,
  progress_message text,
  pid integer,
  log_path text,
  error_message text,
  started_by text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists training_jobs_status_idx
  on public.training_jobs (status);
create index if not exists training_jobs_version_idx
  on public.training_jobs (model_version_id, created_at desc);

create table if not exists public.model_evaluations (
  id uuid primary key default gen_random_uuid(),
  model_version_id uuid not null references public.model_versions(id) on delete cascade,
  passed boolean not null default false,
  metrics_json jsonb not null default '{}'::jsonb,
  compared_to_version_id uuid references public.model_versions(id) on delete set null,
  evaluated_at timestamptz not null default now(),
  notes text
);

create index if not exists model_evaluations_version_idx
  on public.model_evaluations (model_version_id, evaluated_at desc);

create table if not exists public.model_deployments (
  id uuid primary key default gen_random_uuid(),
  model_version_id uuid not null references public.model_versions(id) on delete cascade,
  previous_version_id uuid references public.model_versions(id) on delete set null,
  action text not null
    check (action in ('deploy', 'rollback', 'reject', 'health_fail')),
  success boolean not null default true,
  actor_user_id text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists model_deployments_created_idx
  on public.model_deployments (created_at desc);

comment on table public.model_versions is
  'CNN model registry. Only one row should have is_production=true.';
comment on table public.training_jobs is
  'Background training attempts for candidate model versions.';
comment on table public.model_evaluations is
  'Held-out evaluation results for candidate models.';
comment on table public.model_deployments is
  'Audit log of deploy / rollback / reject actions.';
