-- Private buckets: the backend returns signed URLs only after authorization.
insert into storage.buckets (id, name, public)
values ('tryon-private', 'tryon-private', false), ('product-media', 'product-media', false), ('product-3d', 'product-3d', false)
on conflict (id) do update set public = excluded.public;

create policy "customers upload own tryon source" on storage.objects for insert to authenticated
with check (bucket_id = 'tryon-private' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "customers read own tryon files" on storage.objects for select to authenticated
using (bucket_id = 'tryon-private' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "customers delete own tryon files" on storage.objects for delete to authenticated
using (bucket_id = 'tryon-private' and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "sellers upload own product media" on storage.objects for insert to authenticated
with check (bucket_id in ('product-media', 'product-3d') and exists (select 1 from public.sellers s where s.id = ((storage.foldername(name))[1])::uuid and s.user_id = (select auth.uid())));
create policy "sellers manage own product media" on storage.objects for all to authenticated
using (bucket_id in ('product-media', 'product-3d') and exists (select 1 from public.sellers s where s.id = ((storage.foldername(name))[1])::uuid and s.user_id = (select auth.uid())))
with check (bucket_id in ('product-media', 'product-3d') and exists (select 1 from public.sellers s where s.id = ((storage.foldername(name))[1])::uuid and s.user_id = (select auth.uid())));
create policy "admins manage product media" on storage.objects for all to authenticated
using (bucket_id in ('product-media', 'product-3d') and exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
with check (bucket_id in ('product-media', 'product-3d') and exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));

alter table public.stock_movements enable row level security;
create policy "sellers read own stock movements" on public.stock_movements for select to authenticated
using (exists (select 1 from public.product_variants v join public.products p on p.id = v.product_id join public.sellers s on s.id = p.seller_id where v.id = variant_id and s.user_id = (select auth.uid())));
create policy "admins read stock movements" on public.stock_movements for select to authenticated
using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));

create or replace function public.adjust_inventory(p_variant_id uuid, p_quantity_delta integer, p_reason text)
returns public.inventory
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_inventory public.inventory;
  v_is_admin boolean;
begin
  if p_quantity_delta = 0 then raise exception 'Inventory delta cannot be zero'; end if;
  v_is_admin := exists (select 1 from public.profiles where id = (select auth.uid()) and role = 'admin');
  if not v_is_admin and not exists (select 1 from public.product_variants v join public.products p on p.id = v.product_id join public.sellers s on s.id = p.seller_id where v.id = p_variant_id and s.user_id = (select auth.uid())) then
    raise exception 'Not allowed to adjust this inventory';
  end if;
  select * into v_inventory from public.inventory where variant_id = p_variant_id for update;
  if not found then raise exception 'Inventory record not found'; end if;
  if v_inventory.quantity + p_quantity_delta < 0 then raise exception 'Inventory cannot become negative'; end if;
  update public.inventory set quantity = quantity + p_quantity_delta, updated_at = now() where variant_id = p_variant_id returning * into v_inventory;
  insert into public.stock_movements (variant_id, quantity_delta, reason) values (p_variant_id, p_quantity_delta, p_reason);
  return v_inventory;
end;
$$;

revoke execute on function public.adjust_inventory(uuid, integer, text) from public, anon;
grant execute on function public.adjust_inventory(uuid, integer, text) to authenticated;
