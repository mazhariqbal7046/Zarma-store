create policy "admins manage seller applications" on public.seller_applications for all to authenticated
using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));

create policy "sellers manage own seller profile" on public.sellers for update to authenticated
using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "admins manage sellers" on public.sellers for all to authenticated
using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));

create policy "sellers manage own shop" on public.shops for all to authenticated
using (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid())))
with check (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid())));
create policy "admins manage shops" on public.shops for all to authenticated
using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));

create policy "sellers manage own products" on public.products for all to authenticated
using (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid())))
with check (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid())));
create policy "admins manage products" on public.products for all to authenticated
using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));

create policy "sellers manage own variants" on public.product_variants for all to authenticated
using (exists (select 1 from public.products p join public.sellers s on s.id = p.seller_id where p.id = product_id and s.user_id = (select auth.uid())))
with check (exists (select 1 from public.products p join public.sellers s on s.id = p.seller_id where p.id = product_id and s.user_id = (select auth.uid())));
create policy "sellers manage own images" on public.product_images for all to authenticated
using (exists (select 1 from public.products p join public.sellers s on s.id = p.seller_id where p.id = product_id and s.user_id = (select auth.uid())))
with check (exists (select 1 from public.products p join public.sellers s on s.id = p.seller_id where p.id = product_id and s.user_id = (select auth.uid())));
create policy "sellers manage own inventory" on public.inventory for all to authenticated
using (exists (select 1 from public.product_variants v join public.products p on p.id = v.product_id join public.sellers s on s.id = p.seller_id where v.id = variant_id and s.user_id = (select auth.uid())))
with check (exists (select 1 from public.product_variants v join public.products p on p.id = v.product_id join public.sellers s on s.id = p.seller_id where v.id = variant_id and s.user_id = (select auth.uid())));
create policy "admins manage variants" on public.product_variants for all to authenticated
using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
create policy "admins manage images" on public.product_images for all to authenticated
using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
create policy "admins manage inventory" on public.inventory for all to authenticated
using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));

create policy "admins manage categories" on public.categories for all to authenticated
using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
