-- Keep the existing classifications table and history rows.
-- Add the requested names beside the columns the website already writes.

alter table public.classifications
  add column if not exists predicted_textile_type text,
  add column if not exists confidence_score numeric(6,5),
  add column if not exists image_reference text,
  add column if not exists image_path text;

update public.classifications
set
  predicted_textile_type = coalesce(predicted_textile_type, predicted_label),
  confidence_score = coalesce(confidence_score, confidence),
  image_reference = coalesce(image_reference, image_path);

create or replace function public.sync_classification_aliases()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.predicted_textile_type is null then
    new.predicted_textile_type := new.predicted_label;
  end if;
  if new.predicted_label is null then
    new.predicted_label := new.predicted_textile_type;
  end if;
  if new.confidence_score is null then
    new.confidence_score := new.confidence;
  end if;
  if new.confidence is null then
    new.confidence := new.confidence_score;
  end if;
  if new.image_reference is null then
    new.image_reference := new.image_path;
  end if;
  if new.image_path is null then
    new.image_path := new.image_reference;
  end if;
  return new;
end;
$$;

drop trigger if exists classifications_sync_aliases on public.classifications;
create trigger classifications_sync_aliases
  before insert or update on public.classifications
  for each row execute function public.sync_classification_aliases();
