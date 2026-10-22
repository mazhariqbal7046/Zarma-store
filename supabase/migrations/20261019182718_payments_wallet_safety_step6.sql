-- Additive financial safety migration. No customer rows are deleted.
alter table public.payments add column if not exists currency text not null default 'PKR';
alter table public.wallets add column if not exists pending_balance_pkr bigint not null default 0;
alter table public.seller_earnings add column if not exists withdrawn_pkr bigint not null default 0;

alter table public.withdrawal_requests drop constraint if exists withdrawal_requests_status_check;
alter table public.withdrawal_requests
  add constraint withdrawal_requests_status_check
  check (status in ('pending', 'approved', 'paid', 'rejected', 'failed'));

create table if not exists public.payment_attempts (
  id uuid primary key default gen_random_uuid(),
  payment_id uuid not null references public.payments(id) on delete cascade,
  provider text not null check (provider in ('jazzcash', 'easypaisa')),
  idempotency_key text not null unique,
  provider_transaction_id text,
  amount_pkr bigint not null check (amount_pkr > 0),
  currency text not null default 'PKR' check (currency = 'PKR'),
  status text not null default 'pending' check (status in ('pending', 'paid', 'failed', 'expired', 'refunded')),
  request_payload jsonb not null default '{}'::jsonb,
  response_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists payment_attempts_provider_reference_key
  on public.payment_attempts(provider, provider_transaction_id)
  where provider_transaction_id is not null;

create table if not exists public.refunds (
  id uuid primary key default gen_random_uuid(),
  payment_id uuid not null references public.payments(id) on delete cascade,
  provider text not null check (provider in ('jazzcash', 'easypaisa')),
  amount_pkr bigint not null check (amount_pkr > 0),
  idempotency_key text not null unique,
  provider_ref text,
  status text not null default 'pending' check (status in ('pending', 'succeeded', 'failed')),
  reason text,
  requested_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists payment_events_provider_event_key
  on public.payment_events(provider, provider_event_id);
create index if not exists payment_attempts_payment_idx
  on public.payment_attempts(payment_id, created_at desc);
create index if not exists refunds_payment_idx
  on public.refunds(payment_id, created_at desc);

alter table public.payment_attempts enable row level security;
alter table public.refunds enable row level security;

do $$
begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='payment_attempts' and policyname='customers read own payment attempts') then
    create policy "customers read own payment attempts" on public.payment_attempts
      for select to authenticated
      using (exists (select 1 from public.payments p join public.orders o on o.id = p.order_id where p.id = payment_id and o.user_id = (select auth.uid())));
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='refunds' and policyname='customers read own refunds') then
    create policy "customers read own refunds" on public.refunds
      for select to authenticated
      using (exists (select 1 from public.payments p join public.orders o on o.id = p.order_id where p.id = payment_id and o.user_id = (select auth.uid())));
  end if;
end $$;

create or replace function public.begin_payment_attempt(
  p_order_id uuid,
  p_provider text,
  p_idempotency_key text
)
returns public.payment_attempts
language plpgsql security definer set search_path = public
as $$
declare
  v_order public.orders;
  v_payment public.payments;
  v_attempt public.payment_attempts;
begin
  if auth.uid() is null then raise exception 'Authenticated customer required'; end if;
  if p_provider not in ('jazzcash', 'easypaisa') then raise exception 'Unsupported payment provider'; end if;
  if p_idempotency_key is null or length(trim(p_idempotency_key)) < 8 then raise exception 'Valid idempotency key required'; end if;

  select * into v_order from public.orders where id = p_order_id and user_id = auth.uid() for update;
  if not found then raise exception 'Order not found'; end if;
  if v_order.status in ('cancelled', 'delivered') then raise exception 'Order cannot receive a payment'; end if;
  select * into v_payment from public.payments where order_id = p_order_id order by id limit 1 for update;
  if not found then raise exception 'Payment record not found'; end if;
  if v_payment.status in ('paid', 'refunded') then raise exception 'Payment is already finalized'; end if;

  select * into v_attempt from public.payment_attempts where idempotency_key = p_idempotency_key;
  if found then
    if v_attempt.payment_id <> v_payment.id or v_attempt.provider <> p_provider then raise exception 'Idempotency key belongs to another payment'; end if;
    return v_attempt;
  end if;

  update public.payments set provider = p_provider where id = v_payment.id;
  insert into public.payment_attempts(payment_id, provider, idempotency_key, amount_pkr)
    values (v_payment.id, p_provider, p_idempotency_key, v_order.total_pkr)
    returning * into v_attempt;
  return v_attempt;
end $$;

revoke all on function public.begin_payment_attempt(uuid, text, text) from public, anon;
grant execute on function public.begin_payment_attempt(uuid, text, text) to authenticated;

create or replace function public.process_payment_event(
  p_payment_id uuid,
  p_provider text,
  p_provider_event_id text,
  p_event_type text,
  p_status text,
  p_provider_reference text,
  p_amount_pkr bigint,
  p_payload jsonb
)
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare
  v_payment public.payments;
  v_order public.orders;
  v_event_id uuid;
  v_wallet public.wallets;
  v_refund_amount bigint;
  v_refunded bigint;
  v_tx_id uuid;
begin
  if coalesce(current_setting('request.jwt.claim.role', true), '') not in ('service_role', 'authenticated') then
    raise exception 'Trusted backend role required';
  end if;
  if p_provider not in ('jazzcash', 'easypaisa') then raise exception 'Unsupported payment provider'; end if;
  if p_status not in ('pending', 'paid', 'failed', 'refunded') then raise exception 'Invalid payment status'; end if;
  if p_provider_event_id is null or length(trim(p_provider_event_id)) < 3 then raise exception 'Provider event id required'; end if;

  insert into public.payment_events(payment_id, provider, provider_event_id, event_type, payload)
    values (p_payment_id, p_provider, p_provider_event_id, p_event_type, coalesce(p_payload, '{}'::jsonb))
    on conflict (provider, provider_event_id) do nothing
    returning id into v_event_id;
  if v_event_id is null then return jsonb_build_object('accepted', true, 'duplicate', true); end if;

  select p.* into v_payment from public.payments p where p.id = p_payment_id for update;
  if not found then raise exception 'Payment not found'; end if;
  select o.* into v_order from public.orders o where o.id = v_payment.order_id for update;
  if v_payment.provider <> p_provider then raise exception 'Payment provider mismatch'; end if;

  if p_status in ('paid', 'refunded') and (p_amount_pkr is null or p_amount_pkr <= 0) then raise exception 'Verified amount required'; end if;
  if p_status = 'paid' and p_amount_pkr <> v_order.total_pkr then raise exception 'Payment amount mismatch'; end if;
  if p_status = 'paid' and v_payment.status = 'paid' then return jsonb_build_object('accepted', true, 'duplicate', true, 'reason', 'already_paid'); end if;
  if p_status = 'refunded' and v_payment.status = 'refunded' then return jsonb_build_object('accepted', true, 'duplicate', true, 'reason', 'already_refunded'); end if;

  if p_status = 'paid' then
    update public.payments set status='paid', provider_reference=p_provider_reference, verified_at=now() where id=p_payment_id;
    update public.orders set status='confirmed' where id=v_order.id and status='pending';
  elsif p_status = 'failed' then
    if v_payment.status in ('paid', 'refunded') then raise exception 'Finalized payment cannot become failed'; end if;
    update public.payments set status='failed', provider_reference=p_provider_reference where id=p_payment_id;
  elsif p_status = 'pending' then
    update public.payments set status='pending', provider_reference=p_provider_reference where id=p_payment_id;
  elsif p_status = 'refunded' then
    if v_payment.status <> 'paid' then raise exception 'Only a paid payment can be refunded'; end if;
    select coalesce(sum(amount_pkr) filter (where status='succeeded'), 0) into v_refunded from public.refunds where payment_id=p_payment_id;
    v_refund_amount := p_amount_pkr;
    if v_refund_amount > v_order.total_pkr - v_refunded then raise exception 'Refund exceeds refundable amount'; end if;
    insert into public.refunds(payment_id, provider, amount_pkr, idempotency_key, provider_ref, status, reason)
      values (p_payment_id, p_provider, v_refund_amount, 'event:' || p_provider || ':' || p_provider_event_id, p_provider_reference, 'succeeded', 'Provider-confirmed refund');
    update public.payments set status='refunded', provider_reference=p_provider_reference, verified_at=now() where id=p_payment_id;
    insert into public.wallets(user_id, balance_pkr, pending_balance_pkr) values (v_order.user_id, 0, 0)
      on conflict (user_id) do nothing;
    select * into v_wallet from public.wallets where user_id=v_order.user_id for update;
    insert into public.wallet_transactions(wallet_id, amount_pkr, kind, reference_type, reference_id, idempotency_key, metadata)
      values (v_wallet.id, v_refund_amount, 'refund', 'payment', p_payment_id, 'refund:' || p_provider || ':' || p_provider_event_id, jsonb_build_object('provider', p_provider))
      on conflict (idempotency_key) do nothing
      returning id into v_tx_id;
    if v_tx_id is not null then
      update public.wallets set balance_pkr=balance_pkr + v_refund_amount, updated_at=now() where id=v_wallet.id;
    end if;
  end if;

  insert into public.audit_logs(actor_id, action, entity_type, entity_id, metadata)
    values (null, 'payment.event.accepted', 'payment', p_payment_id, jsonb_build_object('provider',p_provider,'event_id',p_provider_event_id,'status',p_status));
  return jsonb_build_object('accepted', true, 'duplicate', false, 'status', p_status);
end $$;

revoke all on function public.process_payment_event(uuid, text, text, text, text, text, bigint, jsonb) from public, anon, authenticated;
grant execute on function public.process_payment_event(uuid, text, text, text, text, text, bigint, jsonb) to service_role;

create or replace function public.create_refund_request(
  p_payment_id uuid,
  p_amount_pkr bigint,
  p_idempotency_key text,
  p_reason text default null
)
returns public.refunds
language plpgsql security definer set search_path = public
as $$
declare
  v_payment public.payments;
  v_order public.orders;
  v_refund public.refunds;
  v_used bigint;
begin
  if not exists (select 1 from public.profiles where id=auth.uid() and role='admin') then raise exception 'Admin role required'; end if;
  if p_amount_pkr is null or p_amount_pkr <= 0 then raise exception 'Refund amount must be positive'; end if;
  if p_idempotency_key is null or length(trim(p_idempotency_key)) < 8 then raise exception 'Valid idempotency key required'; end if;
  select p.* into v_payment from public.payments p where p.id=p_payment_id for update;
  if not found then raise exception 'Payment not found'; end if;
  select o.* into v_order from public.orders o where o.id=v_payment.order_id;
  if v_payment.status <> 'paid' then raise exception 'Only paid payments can be refunded'; end if;
  select coalesce(sum(amount_pkr),0) into v_used from public.refunds where payment_id=p_payment_id and status in ('pending','succeeded');
  if p_amount_pkr > v_order.total_pkr - v_used then raise exception 'Refund exceeds refundable amount'; end if;
  insert into public.refunds(payment_id, provider, amount_pkr, idempotency_key, requested_by, reason)
    values (p_payment_id, v_payment.provider, p_amount_pkr, p_idempotency_key, auth.uid(), p_reason)
    on conflict (idempotency_key) do update set idempotency_key=excluded.idempotency_key
    returning * into v_refund;
  return v_refund;
end $$;

revoke all on function public.create_refund_request(uuid, bigint, text, text) from public, anon;
grant execute on function public.create_refund_request(uuid, bigint, text, text) to authenticated;

create or replace function public.admin_set_withdrawal_status(
  p_withdrawal_id uuid,
  p_status text,
  p_payout_reference text default null
)
returns public.withdrawal_requests
language plpgsql security definer set search_path = public
as $$
declare
  v_request public.withdrawal_requests;
  v_earning public.seller_earnings;
  v_remaining bigint;
  v_alloc bigint;
begin
  if not exists (select 1 from public.profiles where id=auth.uid() and role='admin') then raise exception 'Admin role required'; end if;
  if p_status not in ('approved','rejected','paid','failed') then raise exception 'Invalid withdrawal status'; end if;
  select * into v_request from public.withdrawal_requests where id=p_withdrawal_id for update;
  if not found then raise exception 'Withdrawal not found'; end if;
  if p_status='approved' and v_request.status <> 'pending' then raise exception 'Only pending withdrawals can be approved'; end if;
  if p_status in ('rejected','failed') and v_request.status not in ('pending','approved') then raise exception 'Withdrawal is not reviewable'; end if;
  if p_status='paid' then
    if v_request.status <> 'approved' or p_payout_reference is null or length(trim(p_payout_reference)) < 3 then raise exception 'Approved withdrawal and payout reference required'; end if;
    v_remaining := v_request.amount_pkr;
    for v_earning in select * from public.seller_earnings where seller_id=v_request.seller_id and status='available' and net_pkr-withdrawn_pkr > 0 order by created_at, id for update loop
      exit when v_remaining <= 0;
      v_alloc := least(v_remaining, v_earning.net_pkr-v_earning.withdrawn_pkr);
      update public.seller_earnings set withdrawn_pkr=withdrawn_pkr+v_alloc, status=case when withdrawn_pkr+v_alloc >= net_pkr then 'paid' else status end where id=v_earning.id;
      v_remaining := v_remaining-v_alloc;
    end loop;
    if v_remaining > 0 then raise exception 'Insufficient unwithdrawn seller earnings'; end if;
  end if;
  update public.withdrawal_requests set status=p_status, payout_reference=coalesce(p_payout_reference,payout_reference), reviewed_by=auth.uid() where id=p_withdrawal_id returning * into v_request;
  insert into public.audit_logs(actor_id, action, entity_type, entity_id, metadata)
    values (auth.uid(), 'withdrawal.status.changed', 'withdrawal', p_withdrawal_id, jsonb_build_object('status',p_status));
  return v_request;
end $$;

revoke all on function public.admin_set_withdrawal_status(uuid, text, text) from public, anon;
grant execute on function public.admin_set_withdrawal_status(uuid, text, text) to authenticated;

create or replace function public.request_seller_withdrawal(
  p_amount_pkr bigint,
  p_payout_method text,
  p_payout_reference text default null,
  p_idempotency_key text default null
)
returns public.withdrawal_requests
language plpgsql security invoker set search_path = public
as $$
declare
  v_seller_id uuid; v_request public.withdrawal_requests; v_available bigint; v_locked bigint;
begin
  if p_amount_pkr is null or p_amount_pkr <= 0 then raise exception 'Withdrawal amount must be positive'; end if;
  if p_idempotency_key is null or length(trim(p_idempotency_key)) < 8 then raise exception 'Valid idempotency key required'; end if;
  select id into v_seller_id from public.sellers where user_id = (select auth.uid()) and active = true;
  if v_seller_id is null then raise exception 'Approved seller account required'; end if;
  select * into v_request from public.withdrawal_requests where seller_id = v_seller_id and idempotency_key = p_idempotency_key;
  if found then return v_request; end if;
  perform 1 from public.seller_earnings where seller_id = v_seller_id for update;
  perform 1 from public.withdrawal_requests where seller_id = v_seller_id and status in ('pending', 'approved') for update;
  select coalesce(sum(greatest(net_pkr-withdrawn_pkr,0)) filter (where status in ('available','paid')), 0) into v_available from public.seller_earnings where seller_id = v_seller_id;
  select coalesce(sum(amount_pkr), 0) into v_locked from public.withdrawal_requests where seller_id = v_seller_id and status in ('pending', 'approved');
  if p_amount_pkr > v_available - v_locked then raise exception 'Insufficient available seller balance'; end if;
  insert into public.withdrawal_requests(seller_id, amount_pkr, payout_method, payout_reference, idempotency_key)
    values (v_seller_id, p_amount_pkr, p_payout_method, p_payout_reference, p_idempotency_key)
    returning * into v_request;
  return v_request;
end $$;

revoke execute on function public.request_seller_withdrawal(bigint, text, text, text) from public, anon;
grant execute on function public.request_seller_withdrawal(bigint, text, text, text) to authenticated;
