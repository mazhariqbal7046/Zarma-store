-- Restrict internal tables and add the minimum row ownership policies required by APIs.
alter table public.outfit_recommendations enable row level security;
alter table public.notification_events enable row level security;
alter table public.audit_logs enable row level security;

create policy "public read outfit recommendations" on public.outfit_recommendations
  for select to anon, authenticated using (true);
create policy "admins read audit logs" on public.audit_logs
  for select to authenticated using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));

create policy "users insert own search logs" on public.ai_search_logs
  for insert to authenticated with check (user_id = (select auth.uid()));
create policy "users read own search logs" on public.ai_search_logs
  for select to authenticated using (user_id = (select auth.uid()));
create policy "admins read commissions" on public.commission_records
  for select to authenticated using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
create policy "sellers read own commissions" on public.commission_records
  for select to authenticated using (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid())));
create policy "sellers manage own discounts" on public.discounts
  for all to authenticated using (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid())))
  with check (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid())));
create policy "admins manage discounts" on public.discounts
  for all to authenticated using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
  with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));

create policy "admins read all support conversations" on public.conversations
  for select to authenticated using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
create policy "admins update support conversations" on public.conversations
  for update to authenticated using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
  with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
create policy "admins read support messages" on public.messages
  for select to authenticated using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
create policy "admins send support messages" on public.messages
  for insert to authenticated with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin') and sender_id = (select auth.uid()) and sender_type = 'admin');

create policy "admins manage notifications" on public.notifications
  for all to authenticated using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
  with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
