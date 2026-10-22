-- Step 8 security hardening. Additive controls and policy replacements only.
-- No customer rows are deleted or rewritten.

begin;

alter table public.profiles
  add column if not exists account_status text not null default 'active';

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'profiles_account_status_check'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_account_status_check
      check (account_status in ('active', 'suspended', 'closed'));
  end if;
end
$$;

-- Authorization state is server-managed; profile self-editing must never include it.
create or replace function private.prevent_profile_privilege_escalation()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  request_role text := coalesce(current_setting('request.jwt.claim.role', true), '');
begin
  if (new.role is distinct from old.role or new.account_status is distinct from old.account_status)
     and request_role not in ('service_role')
     and current_user not in ('postgres', 'supabase_admin') then
    raise exception 'Authorization state is server managed';
  end if;
  return new;
end;
$$;
revoke all on function private.prevent_profile_privilege_escalation() from public, anon, authenticated;
drop trigger if exists protect_profile_authorization_state on public.profiles;
create trigger protect_profile_authorization_state
before update on public.profiles
for each row execute function private.prevent_profile_privilege_escalation();
revoke update (role, account_status) on public.profiles from anon, authenticated;

-- Seller applications are immutable for applicants after submission; only admins decide them.
drop policy if exists "users manage own seller applications" on public.seller_applications;
drop policy if exists "users read own seller applications" on public.seller_applications;
drop policy if exists "users create own seller applications" on public.seller_applications;
create policy "users read own seller applications" on public.seller_applications
  for select to authenticated using (user_id = (select auth.uid()));
create policy "users create own seller applications" on public.seller_applications
  for insert to authenticated with check (user_id = (select auth.uid()) and status = 'pending');

-- Replace permissive seller policies so a deactivated seller cannot keep changing store data.
drop policy if exists "sellers manage own seller profile" on public.sellers;
create policy "sellers manage own seller profile" on public.sellers
  for update to authenticated
  using (user_id = (select auth.uid()) and active = true)
  with check (user_id = (select auth.uid()) and active = true);

drop policy if exists "sellers manage own shop" on public.shops;
create policy "sellers manage own shop" on public.shops
  for all to authenticated
  using (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid()) and s.active = true))
  with check (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid()) and s.active = true));

drop policy if exists "sellers manage own products" on public.products;
create policy "sellers manage own products" on public.products
  for all to authenticated
  using (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid()) and s.active = true))
  with check (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid()) and s.active = true));

drop policy if exists "sellers manage own variants" on public.product_variants;
create policy "sellers manage own variants" on public.product_variants
  for all to authenticated
  using (exists (select 1 from public.products p join public.sellers s on s.id = p.seller_id where p.id = product_id and s.user_id = (select auth.uid()) and s.active = true))
  with check (exists (select 1 from public.products p join public.sellers s on s.id = p.seller_id where p.id = product_id and s.user_id = (select auth.uid()) and s.active = true));

drop policy if exists "sellers manage own images" on public.product_images;
create policy "sellers manage own images" on public.product_images
  for all to authenticated
  using (exists (select 1 from public.products p join public.sellers s on s.id = p.seller_id where p.id = product_id and s.user_id = (select auth.uid()) and s.active = true))
  with check (exists (select 1 from public.products p join public.sellers s on s.id = p.seller_id where p.id = product_id and s.user_id = (select auth.uid()) and s.active = true));

drop policy if exists "sellers manage own inventory" on public.inventory;
create policy "sellers manage own inventory" on public.inventory
  for all to authenticated
  using (exists (select 1 from public.product_variants v join public.products p on p.id = v.product_id join public.sellers s on s.id = p.seller_id where v.id = variant_id and s.user_id = (select auth.uid()) and s.active = true))
  with check (exists (select 1 from public.product_variants v join public.products p on p.id = v.product_id join public.sellers s on s.id = p.seller_id where v.id = variant_id and s.user_id = (select auth.uid()) and s.active = true));

drop policy if exists "sellers manage own discounts" on public.discounts;
create policy "sellers manage own discounts" on public.discounts
  for all to authenticated
  using (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid()) and s.active = true))
  with check (exists (select 1 from public.sellers s where s.id = seller_id and s.user_id = (select auth.uid()) and s.active = true));

drop policy if exists "sellers read own 3d assets" on public.product_3d_assets;
create policy "sellers read own 3d assets" on public.product_3d_assets
  for select to authenticated
  using (exists (select 1 from public.products p join public.sellers s on s.id = p.seller_id where p.id = product_id and s.user_id = (select auth.uid()) and s.active = true));

drop policy if exists "sellers read own stock movements" on public.stock_movements;
create policy "sellers read own stock movements" on public.stock_movements
  for select to authenticated
  using (exists (select 1 from public.product_variants v join public.products p on p.id = v.product_id join public.sellers s on s.id = p.seller_id where v.id = variant_id and s.user_id = (select auth.uid()) and s.active = true));
drop policy if exists "sellers create own stock movements" on public.stock_movements;
create policy "sellers create own stock movements" on public.stock_movements
  for insert to authenticated
  with check (exists (select 1 from public.product_variants v join public.products p on p.id = v.product_id join public.sellers s on s.id = p.seller_id where v.id = variant_id and s.user_id = (select auth.uid()) and s.active = true));
drop policy if exists "admins insert stock movements" on public.stock_movements;
create policy "admins insert stock movements" on public.stock_movements
  for insert to authenticated
  with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));

-- A seller storage path must identify both the seller and a product owned by that seller.
drop policy if exists "sellers upload own product media" on storage.objects;
drop policy if exists "sellers manage own product media" on storage.objects;
create policy "sellers upload own product media" on storage.objects
  for insert to authenticated
  with check (
    bucket_id in ('product-media', 'product-3d')
    and exists (
      select 1 from public.products p join public.sellers s on s.id = p.seller_id
      where s.id::text = (storage.foldername(name))[1]
        and p.id::text = (storage.foldername(name))[2]
        and s.user_id = (select auth.uid()) and s.active = true
    )
  );
create policy "sellers manage own product media" on storage.objects
  for all to authenticated
  using (
    bucket_id in ('product-media', 'product-3d')
    and exists (
      select 1 from public.products p join public.sellers s on s.id = p.seller_id
      where s.id::text = (storage.foldername(name))[1]
        and p.id::text = (storage.foldername(name))[2]
        and s.user_id = (select auth.uid()) and s.active = true
    )
  )
  with check (
    bucket_id in ('product-media', 'product-3d')
    and exists (
      select 1 from public.products p join public.sellers s on s.id = p.seller_id
      where s.id::text = (storage.foldername(name))[1]
        and p.id::text = (storage.foldername(name))[2]
        and s.user_id = (select auth.uid()) and s.active = true
    )
  );

-- Customers may only create customer messages for their own conversation.
drop policy if exists "users create own messages" on public.messages;
drop policy if exists "users create own customer messages" on public.messages;
create policy "users create own customer messages" on public.messages
  for insert to authenticated
  with check (
    sender_id = (select auth.uid())
    and sender_type = 'customer'
    and exists (select 1 from public.conversations c where c.id = conversation_id and c.user_id = (select auth.uid()))
  );

-- User-facing updates are routed through ownership-checked RPCs, not arbitrary column updates.
revoke update (user_id, support_ticket_id, handoff_requested, handoff_reason, handoff_at, ai_context, last_read_at)
  on public.conversations from authenticated;
revoke update (user_id, type, title, body, data, dedupe_key, created_at)
  on public.notifications from authenticated;

-- A generated order total and discount must never become negative or exceed the payable amount.
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'orders_total_nonnegative' and conrelid = 'public.orders'::regclass) then
    alter table public.orders add constraint orders_total_nonnegative check (total_pkr >= 0);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'orders_discount_bound' and conrelid = 'public.orders'::regclass) then
    alter table public.orders add constraint orders_discount_bound check (discount_pkr <= subtotal_pkr + delivery_pkr);
  end if;
end
$$;

create or replace function public.create_order(
  p_idempotency_key text,
  p_address_id uuid,
  p_items jsonb,
  p_delivery_pkr integer default 0,
  p_discount_pkr integer default 0
)
returns public.orders
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid := (select auth.uid());
  v_order public.orders;
  v_item jsonb;
  v_variant public.product_variants;
  v_product public.products;
  v_inventory public.inventory;
  v_quantity integer;
  v_unit_price integer;
  v_product_name text;
  v_product_price integer;
  v_subtotal integer := 0;
  v_delivery integer := greatest(coalesce(p_delivery_pkr, 0), 0);
begin
  if v_user_id is null then raise exception 'Authentication required'; end if;
  if p_idempotency_key is null or length(trim(p_idempotency_key)) < 8 then raise exception 'Invalid idempotency key'; end if;
  if not exists (select 1 from public.addresses where id = p_address_id and user_id = v_user_id) then raise exception 'Invalid address'; end if;
  if jsonb_typeof(p_items) <> 'array' or jsonb_array_length(p_items) = 0 or jsonb_array_length(p_items) > 100 then raise exception 'Invalid cart size'; end if;
  if coalesce(p_discount_pkr, 0) <> 0 then raise exception 'Discount must be validated server-side'; end if;

  select * into v_order from public.orders where idempotency_key = p_idempotency_key and user_id = v_user_id;
  if found then return v_order; end if;

  for v_item in select * from jsonb_array_elements(p_items) loop
    begin v_quantity := (v_item->>'quantity')::integer; exception when others then raise exception 'Invalid quantity'; end;
    if v_quantity is null or v_quantity < 1 or v_quantity > 100 then raise exception 'Invalid quantity'; end if;
    begin select * into v_variant from public.product_variants where id = (v_item->>'variant_id')::uuid; exception when others then raise exception 'Invalid product variant'; end;
    if not found then raise exception 'Invalid product variant'; end if;
    select * into v_product from public.products where id = v_variant.product_id and active = true;
    if not found then raise exception 'Product is unavailable'; end if;
    select * into v_inventory from public.inventory where variant_id = v_variant.id for update;
    if not found or v_inventory.quantity - v_inventory.reserved_quantity < v_quantity then raise exception 'Insufficient stock for %', v_product.name; end if;
    v_unit_price := coalesce(v_variant.price_pkr, v_product.price_pkr);
    v_subtotal := v_subtotal + (v_unit_price * v_quantity);
  end loop;

  insert into public.orders (user_id, address_id, subtotal_pkr, delivery_pkr, discount_pkr, idempotency_key)
  values (v_user_id, p_address_id, v_subtotal, v_delivery, 0, p_idempotency_key)
  returning * into v_order;

  for v_item in select * from jsonb_array_elements(p_items) loop
    v_quantity := (v_item->>'quantity')::integer;
    select pv.* into v_variant from public.product_variants pv where pv.id = (v_item->>'variant_id')::uuid;
    select p.name, p.price_pkr into v_product_name, v_product_price from public.products p where p.id = v_variant.product_id;
    v_unit_price := coalesce(v_variant.price_pkr, v_product_price);
    insert into public.order_items (order_id, variant_id, product_name, size, color, quantity, unit_price_pkr)
    values (v_order.id, v_variant.id, v_product_name, v_variant.size, v_variant.color, v_quantity, v_unit_price);
    update public.inventory set reserved_quantity = reserved_quantity + v_quantity, updated_at = now() where variant_id = v_variant.id;
  end loop;

  insert into public.payments (order_id, provider, status) values (v_order.id, 'cash_on_delivery', 'pending');
  insert into public.notification_events (event_key, event_type, payload) values ('order:' || v_order.id, 'order.created', jsonb_build_object('order_id', v_order.id, 'user_id', v_user_id));
  return v_order;
end;
$$;
revoke all on function public.create_order(text, uuid, jsonb, integer, integer) from public, anon;
grant execute on function public.create_order(text, uuid, jsonb, integer, integer) to authenticated;

-- Bind signed provider events to the payment attempt created for the same order.
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
  v_attempt_id uuid;
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
    if v_attempt.provider_transaction_id is null then
      update public.payment_attempts set provider_transaction_id = left(replace(v_attempt.id::text, '-', ''), 20), updated_at = now() where id = v_attempt.id returning * into v_attempt;
    end if;
    return v_attempt;
  end if;

  v_attempt_id := gen_random_uuid();
  update public.payments set provider = p_provider, currency = 'PKR' where id = v_payment.id;
  insert into public.payment_attempts(id, payment_id, provider, idempotency_key, provider_transaction_id, amount_pkr, currency)
    values (v_attempt_id, v_payment.id, p_provider, p_idempotency_key, left(replace(v_attempt_id::text, '-', ''), 20), v_order.total_pkr, 'PKR')
    returning * into v_attempt;
  return v_attempt;
end
$$;

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
  v_attempt public.payment_attempts;
  v_event_id uuid;
  v_wallet public.wallets;
  v_refund_amount bigint;
  v_refunded bigint;
  v_tx_id uuid;
  v_currency text;
begin
  if coalesce(current_setting('request.jwt.claim.role', true), '') <> 'service_role' then
    raise exception 'Trusted backend role required';
  end if;
  if p_provider not in ('jazzcash', 'easypaisa') then raise exception 'Unsupported payment provider'; end if;
  if p_status not in ('pending', 'paid', 'failed', 'refunded') then raise exception 'Invalid payment status'; end if;
  if p_provider_event_id is null or length(trim(p_provider_event_id)) < 3 then raise exception 'Provider event id required'; end if;
  v_currency := upper(coalesce(p_payload->>'pp_TxnCurrency', p_payload->>'currency', 'PKR'));
  if v_currency <> 'PKR' then raise exception 'Unsupported payment currency'; end if;

  select p.* into v_payment from public.payments p where p.id = p_payment_id for update;
  if not found then raise exception 'Payment not found'; end if;
  if v_payment.provider <> p_provider then raise exception 'Payment provider mismatch'; end if;
  select * into v_attempt from public.payment_attempts pa
    where pa.payment_id = p_payment_id
      and (pa.provider_transaction_id = p_provider_event_id or pa.provider_transaction_id = p_provider_reference)
    order by pa.created_at desc limit 1;
  if not found then raise exception 'Provider event is not bound to this payment attempt'; end if;
  select o.* into v_order from public.orders o where o.id = v_payment.order_id for update;

  insert into public.payment_events(payment_id, provider, provider_event_id, event_type, payload)
    values (p_payment_id, p_provider, p_provider_event_id, p_event_type, coalesce(p_payload, '{}'::jsonb))
    on conflict (provider, provider_event_id) do nothing
    returning id into v_event_id;
  if v_event_id is null then return jsonb_build_object('accepted', true, 'duplicate', true); end if;

  if p_status in ('paid', 'refunded') and (p_amount_pkr is null or p_amount_pkr <= 0) then raise exception 'Verified amount required'; end if;
  if p_status = 'paid' and p_amount_pkr <> v_order.total_pkr then raise exception 'Payment amount mismatch'; end if;
  if p_status = 'paid' and v_payment.status = 'paid' then return jsonb_build_object('accepted', true, 'duplicate', true, 'reason', 'already_paid'); end if;
  if p_status = 'refunded' and v_payment.status = 'refunded' then return jsonb_build_object('accepted', true, 'duplicate', true, 'reason', 'already_refunded'); end if;

  update public.payment_attempts set status = p_status, updated_at = now() where id = v_attempt.id;
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
      on conflict (idempotency_key) do nothing returning id into v_tx_id;
    if v_tx_id is not null then update public.wallets set balance_pkr=balance_pkr + v_refund_amount, updated_at=now() where id=v_wallet.id; end if;
  end if;

  insert into public.audit_logs(actor_id, action, entity_type, entity_id, metadata)
    values (null, 'payment.event.accepted', 'payment', p_payment_id, jsonb_build_object('provider',p_provider,'event_id',p_provider_event_id,'status',p_status));
  return jsonb_build_object('accepted', true, 'duplicate', false, 'status', p_status);
end
$$;

revoke all on function public.process_payment_event(uuid, text, text, text, text, text, bigint, jsonb) from public, anon, authenticated;
grant execute on function public.process_payment_event(uuid, text, text, text, text, text, bigint, jsonb) to service_role;

commit;
