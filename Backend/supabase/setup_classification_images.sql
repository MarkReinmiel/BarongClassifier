-- Private photos for classification history.
-- Path shape: {user full name}/{YYYY-MM-DD}/{HHMMSS-filename.jpg}
-- Access is limited to the user who uploaded the file (owner_id).

alter table public.classifications
  add column if not exists image_path text;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'classification-images',
  'classification-images',
  false,
  20971520,
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update
set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Users upload own classification images" on storage.objects;
create policy "Users upload own classification images"
on storage.objects for insert to authenticated
with check (bucket_id = 'classification-images');

drop policy if exists "Users read own classification images" on storage.objects;
create policy "Users read own classification images"
on storage.objects for select to authenticated
using (
  bucket_id = 'classification-images'
  and owner_id = (select auth.uid()::text)
);
