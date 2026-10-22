create extension if not exists pgcrypto;

create type public.user_role as enum ('customer', 'staff', 'admin');
create type public.order_status as enum ('pending', 'confirmed', 'packed', 'shipped', 'delivered', 'cancelled');

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text, phone text, role public.user_role not null default 'customer',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table public.categories (id uuid primary key default gen_random_uuid(), name text not null unique, slug text not null unique, active boolean not null default true);
create table public.products (id uuid primary key default gen_random_uuid(), category_id uuid references public.categories(id), name text not null, slug text not null unique, description text, price_pkr integer not null check (price_pkr >= 0), active boolean not null default true, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create table public.product_variants (id uuid primary key default gen_random_uuid(), product_id uuid not null references public.products(id) on delete cascade, sku text not null unique, size text not null, color text not null, price_pkr integer check (price_pkr >= 0));
create table public.product_images (id uuid primary key default gen_random_uuid(), product_id uuid not null references public.products(id) on delete cascade, storage_path text not null, alt_text text, sort_order integer not null default 0);
create table public.inventory (variant_id uuid primary key references public.product_variants(id) on delete cascade, quantity integer not null default 0 check (quantity >= 0), reserved_quantity integer not null default 0 check (reserved_quantity >= 0), updated_at timestamptz not null default now(), check (reserved_quantity <= quantity));
create table public.outfit_recommendations (id uuid primary key default gen_random_uuid(), source_product_id uuid not null references public.products(id) on delete cascade, recommended_product_id uuid not null references public.products(id) on delete cascade, score numeric(5,2) not null default 0, rule jsonb not null default '{}'::jsonb, unique(source_product_id, recommended_product_id));
create table public.shopping_carts (id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade, status text not null default 'active' check (status in ('active','converted','abandoned')), created_at timestamptz not null default now());
create table public.cart_items (id uuid primary key default gen_random_uuid(), cart_id uuid not null references public.shopping_carts(id) on delete cascade, variant_id uuid not null references public.product_variants(id), quantity integer not null check (quantity > 0), unique(cart_id, variant_id));
create table public.addresses (id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade, label text, recipient_name text not null, phone text not null, line_1 text not null, city text not null, area text, created_at timestamptz not null default now());
create table public.orders (id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id), status public.order_status not null default 'pending', address_id uuid references public.addresses(id), subtotal_pkr integer not null check (subtotal_pkr >= 0), delivery_pkr integer not null default 0 check (delivery_pkr >= 0), discount_pkr integer not null default 0 check (discount_pkr >= 0), total_pkr integer generated always as (subtotal_pkr + delivery_pkr - discount_pkr) stored, idempotency_key text not null unique, created_at timestamptz not null default now());
create table public.order_items (id uuid primary key default gen_random_uuid(), order_id uuid not null references public.orders(id) on delete cascade, variant_id uuid not null references public.product_variants(id), product_name text not null, size text not null, color text not null, quantity integer not null check (quantity > 0), unit_price_pkr integer not null check (unit_price_pkr >= 0));
create table public.payments (id uuid primary key default gen_random_uuid(), order_id uuid not null references public.orders(id) on delete cascade, provider text not null default 'cash_on_delivery', status text not null default 'pending', provider_reference text, verified_at timestamptz);
create table public.ai_conversations (id uuid primary key default gen_random_uuid(), user_id uuid references auth.users(id) on delete set null, locale text not null default 'en', created_at timestamptz not null default now());
create table public.ai_messages (id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.ai_conversations(id) on delete cascade, role text not null check (role in ('user','assistant','tool')), content text not null, tool_name text, created_at timestamptz not null default now());
create table public.stock_movements (id uuid primary key default gen_random_uuid(), variant_id uuid not null references public.product_variants(id), quantity_delta integer not null, reason text not null, order_id uuid references public.orders(id), created_at timestamptz not null default now());
create table public.notification_events (id uuid primary key default gen_random_uuid(), event_key text not null unique, event_type text not null, payload jsonb not null, status text not null default 'pending', attempts integer not null default 0, created_at timestamptz not null default now());
create table public.audit_logs (id uuid primary key default gen_random_uuid(), actor_id uuid references auth.users(id) on delete set null, action text not null, entity_type text not null, entity_id uuid, metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now());

create index products_category_active_idx on public.products(category_id) where active = true;
create index variants_product_idx on public.product_variants(product_id);
create index orders_user_created_idx on public.orders(user_id, created_at desc);
create index ai_messages_conversation_idx on public.ai_messages(conversation_id, created_at);

alter table public.profiles enable row level security; alter table public.categories enable row level security; alter table public.products enable row level security; alter table public.product_variants enable row level security; alter table public.product_images enable row level security; alter table public.inventory enable row level security; alter table public.shopping_carts enable row level security; alter table public.cart_items enable row level security; alter table public.addresses enable row level security; alter table public.orders enable row level security; alter table public.order_items enable row level security; alter table public.payments enable row level security; alter table public.ai_conversations enable row level security; alter table public.ai_messages enable row level security;

create policy "public can read active catalog" on public.products for select to anon, authenticated using (active = true);
create policy "public can read categories" on public.categories for select to anon, authenticated using (active = true);
create policy "public can read product variants" on public.product_variants for select to anon, authenticated using (true);
create policy "public can read product images" on public.product_images for select to anon, authenticated using (true);
create policy "customers own carts" on public.shopping_carts for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "customers own cart items" on public.cart_items for all to authenticated using (exists (select 1 from public.shopping_carts c where c.id = cart_id and c.user_id = (select auth.uid()))) with check (exists (select 1 from public.shopping_carts c where c.id = cart_id and c.user_id = (select auth.uid())));
create policy "customers own profiles" on public.profiles for select to authenticated using ((select auth.uid()) = id);
create policy "customers own addresses" on public.addresses for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "customers own orders" on public.orders for select to authenticated using ((select auth.uid()) = user_id);
create policy "customers own order items" on public.order_items for select to authenticated using (exists (select 1 from public.orders o where o.id = order_id and o.user_id = (select auth.uid())));
create policy "customers own conversations" on public.ai_conversations for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "customers own messages" on public.ai_messages for select to authenticated using (exists (select 1 from public.ai_conversations c where c.id = conversation_id and c.user_id = (select auth.uid())));
