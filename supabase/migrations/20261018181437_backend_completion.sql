-- Additive backend support tables. Existing tables/data are preserved.
create table if not exists public.custom_sizes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null default 'Custom measurements',
  unit text not null default 'cm' check (unit in ('cm', 'in')),
  chest numeric(7,2), waist numeric(7,2), shoulder numeric(7,2), sleeve_length numeric(7,2),
  shirt_length numeric(7,2), inseam numeric(7,2), created_at timestamptz not null default now(),
  check (chest is null or chest > 0), check (waist is null or waist > 0),
  check (shoulder is null or shoulder > 0), check (sleeve_length is null or sleeve_length > 0),
  check (shirt_length is null or shirt_length > 0), check (inseam is null or inseam > 0)
);

create table if not exists public.payment_events (
  id uuid primary key default gen_random_uuid(),
  payment_id uuid references public.payments(id) on delete cascade,
  provider text not null,
  provider_event_id text not null,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(provider, provider_event_id)
);

create table if not exists public.coupons (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  discount_id uuid references public.discounts(id) on delete cascade,
  max_uses integer check (max_uses is null or max_uses > 0),
  used_count integer not null default 0 check (used_count >= 0),
  active boolean not null default true,
  starts_at timestamptz not null default now(),
  ends_at timestamptz
);

create table if not exists public.product_3d_assets (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products(id) on delete cascade,
  storage_path text not null,
  file_type text not null check (file_type in ('model/gltf-binary', 'model/gltf+json', 'application/octet-stream')),
  file_size_bytes bigint not null check (file_size_bytes > 0 and file_size_bytes <= 52428800),
  created_at timestamptz not null default now()
);

alter table public.custom_sizes enable row level security;
alter table public.payment_events enable row level security;
alter table public.coupons enable row level security;
alter table public.product_3d_assets enable row level security;

create policy "users manage own custom sizes" on public.custom_sizes
  for all to authenticated using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
create policy "admins read payment events" on public.payment_events
  for select to authenticated using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
create policy "public read active coupons" on public.coupons
  for select to anon, authenticated using (active = true and starts_at <= now() and (ends_at is null or ends_at > now()));
create policy "sellers read own 3d assets" on public.product_3d_assets
  for select to authenticated using (exists (select 1 from public.products p join public.sellers s on s.id = p.seller_id where p.id = product_id and s.user_id = (select auth.uid())));
create policy "admins manage 3d assets" on public.product_3d_assets
  for all to authenticated using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
  with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));

create index if not exists custom_sizes_user_idx on public.custom_sizes(user_id, created_at desc);
create index if not exists payment_events_payment_idx on public.payment_events(payment_id, created_at desc);
create index if not exists product_3d_assets_product_idx on public.product_3d_assets(product_id);

-- Keep the commission trigger out of the exposed public schema. It is invoked only by PostgreSQL.
create schema if not exists private;
revoke all on schema private from public;
drop trigger if exists order_item_commission_trigger on public.order_items;
drop function if exists public.record_item_commission();

create or replace function private.record_item_commission()
returns trigger language plpgsql security definer set search_path = public, private
as $$
declare v_seller_id uuid; v_gross bigint; v_commission bigint;
begin
  select p.seller_id into v_seller_id from public.order_items oi
    join public.product_variants pv on pv.id = oi.variant_id
    join public.products p on p.id = pv.product_id where oi.id = new.id;
  if v_seller_id is null then return new; end if;
  select coalesce(sum(oi.quantity::bigint * oi.unit_price_pkr::bigint), 0) into v_gross
    from public.order_items oi join public.product_variants pv on pv.id = oi.variant_id
    join public.products p on p.id = pv.product_id
    where oi.order_id = new.order_id and p.seller_id = v_seller_id;
  v_commission := round(v_gross * 0.12);
  insert into public.commission_records(order_id, seller_id, basis_pkr, rate, commission_pkr)
    values (new.order_id, v_seller_id, v_gross, 0.1200, v_commission)
    on conflict (order_id, seller_id) where seller_id is not null
    do update set basis_pkr = excluded.basis_pkr, commission_pkr = excluded.commission_pkr;
  insert into public.seller_earnings(seller_id, order_id, gross_pkr, commission_pkr, net_pkr)
    values (v_seller_id, new.order_id, v_gross, v_commission, v_gross - v_commission)
    on conflict (seller_id, order_id) do update set gross_pkr = excluded.gross_pkr,
      commission_pkr = excluded.commission_pkr, net_pkr = excluded.net_pkr;
  return new;
end; $$;
revoke all on function private.record_item_commission() from public, anon, authenticated;
create trigger order_item_commission_trigger after insert on public.order_items
  for each row execute function private.record_item_commission();
