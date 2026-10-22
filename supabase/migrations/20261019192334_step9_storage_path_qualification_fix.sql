-- Qualify the storage object column explicitly. In a policy subquery, bare `name`
-- can bind to products.name instead of storage.objects.name.
drop policy if exists "sellers manage own product media" on storage.objects;
create policy "sellers manage own product media" on storage.objects
  for all to authenticated
  using (
    bucket_id in ('product-media', 'product-3d')
    and exists (
      select 1 from public.products p join public.sellers s on s.id = p.seller_id
      where s.id::text = (storage.foldername(storage.objects.name))[1]
        and p.id::text = (storage.foldername(storage.objects.name))[2]
        and s.user_id = (select auth.uid()) and s.active = true
    )
  )
  with check (
    bucket_id in ('product-media', 'product-3d')
    and exists (
      select 1 from public.products p join public.sellers s on s.id = p.seller_id
      where s.id::text = (storage.foldername(storage.objects.name))[1]
        and p.id::text = (storage.foldername(storage.objects.name))[2]
        and s.user_id = (select auth.uid()) and s.active = true
    )
  );
