create type public.seller_application_status as enum ('pending', 'approved', 'rejected');
create type public.tryon_job_status as enum ('queued', 'processing', 'completed', 'failed', 'deleted');

alter table public.order_items add column if not exists custom_size jsonb;

create table public.seller_applications (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  business_name text not null, phone text not null, description text, status public.seller_application_status not null default 'pending',
  reviewed_by uuid references auth.users(id), reviewed_at timestamptz, rejection_reason text, created_at timestamptz not null default now()
);
create table public.sellers (
  id uuid primary key default gen_random_uuid(), user_id uuid not null unique references auth.users(id) on delete cascade,
  display_name text not null, slug text not null unique, bio text, approved_at timestamptz not null default now(), active boolean not null default true
);
create table public.shops (
  id uuid primary key default gen_random_uuid(), seller_id uuid not null unique references public.sellers(id) on delete cascade,
  name text not null, slug text not null unique, logo_path text, banner_path text, description text, active boolean not null default true
);
alter table public.products add column if not exists seller_id uuid references public.sellers(id);

create table public.wallets (
  id uuid primary key default gen_random_uuid(), user_id uuid not null unique references auth.users(id) on delete cascade,
  balance_pkr bigint not null default 0 check (balance_pkr >= 0), updated_at timestamptz not null default now()
);
create table public.wallet_transactions (
  id uuid primary key default gen_random_uuid(), wallet_id uuid not null references public.wallets(id) on delete cascade,
  amount_pkr bigint not null check (amount_pkr <> 0), kind text not null check (kind in ('credit','debit','refund','withdrawal','adjustment')),
  reference_type text, reference_id uuid, idempotency_key text not null unique, metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);
create table public.seller_earnings (
  id uuid primary key default gen_random_uuid(), seller_id uuid not null references public.sellers(id), order_id uuid not null references public.orders(id),
  gross_pkr bigint not null check (gross_pkr >= 0), commission_pkr bigint not null check (commission_pkr >= 0), net_pkr bigint not null check (net_pkr >= 0),
  status text not null default 'pending' check (status in ('pending','available','paid','refunded')), created_at timestamptz not null default now(), unique(seller_id, order_id)
);
create table public.commission_records (
  id uuid primary key default gen_random_uuid(), order_id uuid not null references public.orders(id), seller_id uuid references public.sellers(id),
  basis_pkr bigint not null check (basis_pkr >= 0), rate numeric(5,4) not null default 0.1200 check (rate >= 0 and rate <= 1), commission_pkr bigint not null check (commission_pkr >= 0),
  discount_source text not null default 'none', created_at timestamptz not null default now()
);
create table public.withdrawal_requests (
  id uuid primary key default gen_random_uuid(), seller_id uuid not null references public.sellers(id), amount_pkr bigint not null check (amount_pkr > 0),
  payout_method text not null, payout_reference text, status text not null default 'pending' check (status in ('pending','approved','paid','rejected')), reviewed_by uuid references auth.users(id), created_at timestamptz not null default now()
);

create table public.discounts (
  id uuid primary key default gen_random_uuid(), code text not null unique, kind text not null check (kind in ('percentage','fixed')), value_pkr integer not null check (value_pkr >= 0),
  seller_id uuid references public.sellers(id), funded_by text not null default 'platform' check (funded_by in ('platform','seller')), min_subtotal_pkr integer not null default 0,
  max_uses integer, used_count integer not null default 0, starts_at timestamptz not null default now(), ends_at timestamptz, active boolean not null default true
);
create table public.wishlists (
  user_id uuid not null references auth.users(id) on delete cascade, product_id uuid not null references public.products(id) on delete cascade, created_at timestamptz not null default now(), primary key (user_id, product_id)
);
create table public.reviews (
  id uuid primary key default gen_random_uuid(), product_id uuid not null references public.products(id) on delete cascade, user_id uuid not null references auth.users(id) on delete cascade,
  order_id uuid references public.orders(id), rating integer not null check (rating between 1 and 5), title text, body text, approved boolean not null default false, created_at timestamptz not null default now(), unique(product_id, user_id, order_id)
);
create table public.support_tickets (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade, assigned_to uuid references auth.users(id), subject text not null,
  status text not null default 'open' check (status in ('open','pending','resolved','closed')), priority text not null default 'normal' check (priority in ('low','normal','high','urgent')), created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table public.conversations (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade, support_ticket_id uuid references public.support_tickets(id) on delete set null, handoff_requested boolean not null default false, created_at timestamptz not null default now()
);
create table public.messages (
  id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.conversations(id) on delete cascade, sender_id uuid references auth.users(id), sender_type text not null check (sender_type in ('customer','admin','ai')), content text not null, created_at timestamptz not null default now()
);
create table public.ai_search_logs (
  id uuid primary key default gen_random_uuid(), user_id uuid references auth.users(id) on delete set null, query text not null, filters jsonb not null default '{}'::jsonb, result_product_ids uuid[] not null default '{}', created_at timestamptz not null default now()
);
create table public.ai_tryon_jobs (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade, product_id uuid not null references public.products(id), source_image_path text not null,
  result_image_path text, provider text, provider_job_id text, status public.tryon_job_status not null default 'queued', error_message text, created_at timestamptz not null default now(), completed_at timestamptz
);
create table public.notifications (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade, type text not null, title text not null, body text not null, data jsonb not null default '{}'::jsonb, read_at timestamptz, created_at timestamptz not null default now()
);

create index products_seller_idx on public.products(seller_id);
create index seller_earnings_seller_idx on public.seller_earnings(seller_id, created_at desc);
create index wallet_transactions_wallet_idx on public.wallet_transactions(wallet_id, created_at desc);
create index support_tickets_user_idx on public.support_tickets(user_id, updated_at desc);
create index tryon_jobs_user_idx on public.ai_tryon_jobs(user_id, created_at desc);
create index notifications_user_idx on public.notifications(user_id, created_at desc);

alter table public.seller_applications enable row level security;
alter table public.sellers enable row level security;
alter table public.shops enable row level security;
alter table public.wallets enable row level security;
alter table public.wallet_transactions enable row level security;
alter table public.seller_earnings enable row level security;
alter table public.commission_records enable row level security;
alter table public.withdrawal_requests enable row level security;
alter table public.discounts enable row level security;
alter table public.wishlists enable row level security;
alter table public.reviews enable row level security;
alter table public.support_tickets enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.ai_search_logs enable row level security;
alter table public.ai_tryon_jobs enable row level security;
alter table public.notifications enable row level security;

create policy "users manage own seller applications" on public.seller_applications for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "public read active sellers" on public.sellers for select to anon, authenticated using (active = true);
create policy "public read active shops" on public.shops for select to anon, authenticated using (active = true);
create policy "users read own wallet" on public.wallets for select to authenticated using (user_id = (select auth.uid()));
create policy "users read own wallet transactions" on public.wallet_transactions for select to authenticated using (exists (select 1 from public.wallets w where w.id = wallet_id and w.user_id = (select auth.uid())));
create policy "sellers read own earnings" on public.seller_earnings for select to authenticated using (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid())));
create policy "sellers manage own withdrawals" on public.withdrawal_requests for all to authenticated using (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid()))) with check (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid())));
create policy "users manage own wishlist" on public.wishlists for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "public read approved reviews" on public.reviews for select to anon, authenticated using (approved = true or user_id = (select auth.uid()));
create policy "users create own reviews" on public.reviews for insert to authenticated with check (user_id = (select auth.uid()));
create policy "users manage own tickets" on public.support_tickets for select to authenticated using (user_id = (select auth.uid()));
create policy "users create own tickets" on public.support_tickets for insert to authenticated with check (user_id = (select auth.uid()));
create policy "users access own conversations" on public.conversations for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "users access own messages" on public.messages for select to authenticated using (exists (select 1 from public.conversations c where c.id = conversation_id and c.user_id = (select auth.uid())));
create policy "users create own messages" on public.messages for insert to authenticated with check (exists (select 1 from public.conversations c where c.id = conversation_id and c.user_id = (select auth.uid())));
create policy "users access own tryon jobs" on public.ai_tryon_jobs for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "users access own notifications" on public.notifications for select to authenticated using (user_id = (select auth.uid()));
create policy "users update own notification read state" on public.notifications for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
