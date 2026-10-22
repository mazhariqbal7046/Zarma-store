-- Checkout/cancellation are authenticated transaction entry points. They validate auth.uid()
-- internally and need to update reserved inventory/order rows atomically.
alter function public.create_order(text, uuid, jsonb, integer, integer) security definer;
alter function public.create_order(text, uuid, jsonb, integer, integer) set search_path = public;
alter function public.cancel_order(uuid) security definer;
alter function public.cancel_order(uuid) set search_path = public;

create policy "customers update own profiles" on public.profiles
  for update to authenticated using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);
create policy "customers create own ai messages" on public.ai_messages
  for insert to authenticated with check (exists (select 1 from public.ai_conversations c where c.id = conversation_id and c.user_id = (select auth.uid())));
create policy "customers read own payments" on public.payments
  for select to authenticated using (exists (select 1 from public.orders o where o.id = order_id and o.user_id = (select auth.uid())));

create policy "sellers upload own 3d assets" on public.product_3d_assets
  for insert to authenticated with check (exists (select 1 from public.products p join public.sellers s on s.id = p.seller_id where p.id = product_id and s.user_id = (select auth.uid()) and s.active = true));
create policy "sellers delete own 3d assets" on public.product_3d_assets
  for delete to authenticated using (exists (select 1 from public.products p join public.sellers s on s.id = p.seller_id where p.id = product_id and s.user_id = (select auth.uid()) and s.active = true));
