-- Major/revision versioning for model registry.
-- Default training creates v{major}.{revision+1}; new major only when explicitly requested.

alter table public.model_versions
  add column if not exists major_version integer;

alter table public.model_versions
  add column if not exists revision_number integer;

alter table public.model_versions
  add column if not exists dataset_snapshot_id text;

-- Backfill existing rows: treat version_number as major, revision 1.
update public.model_versions
set
  major_version = coalesce(major_version, greatest(version_number, 1)),
  revision_number = coalesce(revision_number, 1)
where major_version is null or revision_number is null;

alter table public.model_versions
  alter column major_version set default 1;

alter table public.model_versions
  alter column revision_number set default 1;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'model_versions_major_revision_uniq'
  ) then
    alter table public.model_versions
      add constraint model_versions_major_revision_uniq
      unique (major_version, revision_number);
  end if;
exception
  when others then
    raise notice 'major/revision unique constraint skipped: %', sqlerrm;
end $$;

create index if not exists model_versions_major_idx
  on public.model_versions (major_version, revision_number desc);

comment on column public.model_versions.major_version is
  'Major model generation (v1, v2, …). New majors only when Owner explicitly requests.';
comment on column public.model_versions.revision_number is
  'Training revision within a major generation (v2.1, v2.2, …).';
