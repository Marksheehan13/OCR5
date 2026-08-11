-- OCR5 persistent invoice image storage.
-- Run this once in the Supabase SQL editor if migrations are not
-- automatically applied by your deployment workflow.

insert into storage.buckets (id, name, public)
values ('invoice-images', 'invoice-images', false)
on conflict (id) do nothing;

create policy "OCR5 anon can upload invoice images"
on storage.objects
for insert
to anon
with check (bucket_id = 'invoice-images');

create policy "OCR5 anon can read invoice images"
on storage.objects
for select
to anon
using (bucket_id = 'invoice-images');
