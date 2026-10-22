-- Step 9: route financial writes through transaction-safe RPCs only.
drop policy if exists "customers can create orders" on public.orders;
drop policy if exists "customers can create order items" on public.order_items;
drop policy if exists "customers can create payments" on public.payments;
revoke insert, update, delete on public.orders from anon, authenticated;
revoke insert, update, delete on public.order_items from anon, authenticated;
revoke insert, update, delete on public.payments from anon, authenticated;

-- Withdrawals are created by the locked/idempotent RPC. Customers can only read their own requests.
drop policy if exists "sellers manage own withdrawals" on public.withdrawal_requests;
drop policy if exists "sellers read own withdrawals" on public.withdrawal_requests;
create policy "sellers read own withdrawals" on public.withdrawal_requests
  for select to authenticated
  using (exists (
    select 1 from public.sellers s
    where s.id = seller_id and s.user_id = (select auth.uid())
  ));
revoke insert, update, delete on public.withdrawal_requests from anon, authenticated;

-- The API calls this function with the customer's bearer token. SECURITY DEFINER is required
-- because direct table writes are revoked; auth.uid() and the active-seller check remain mandatory.
create or replace function public.request_seller_withdrawal(
  p_amount_pkr bigint,
  p_payout_method text,
  p_payout_reference text default null,
  p_idempotency_key text default null
)
returns public.withdrawal_requests
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid := (select auth.uid());
  v_seller_id uuid;
  v_request public.withdrawal_requests;
  v_available bigint;
  v_locked bigint;
begin
  if v_user_id is null then raise exception 'Authentication required'; end if;
  if p_amount_pkr is null or p_amount_pkr <= 0 then raise exception 'Withdrawal amount must be positive'; end if;
  if p_idempotency_key is null or length(trim(p_idempotency_key)) < 8 then raise exception 'Valid idempotency key required'; end if;
  select id into v_seller_id from public.sellers where user_id = v_user_id and active = true;
  if v_seller_id is null then raise exception 'Approved seller account required'; end if;
  select * into v_request from public.withdrawal_requests where seller_id = v_seller_id and idempotency_key = p_idempotency_key;
  if found then return v_request; end if;
  perform 1 from public.seller_earnings where seller_id = v_seller_id for update;
  perform 1 from public.withdrawal_requests where seller_id = v_seller_id and status in ('pending', 'approved') for update;
  select coalesce(sum(net_pkr) filter (where status = 'available'), 0) into v_available
    from public.seller_earnings where seller_id = v_seller_id;
  select coalesce(sum(amount_pkr), 0) into v_locked
    from public.withdrawal_requests where seller_id = v_seller_id and status in ('pending', 'approved');
  if p_amount_pkr > v_available - v_locked then raise exception 'Insufficient available seller balance'; end if;
  insert into public.withdrawal_requests(seller_id, amount_pkr, payout_method, payout_reference, idempotency_key)
    values (v_seller_id, p_amount_pkr, p_payout_method, p_payout_reference, p_idempotency_key)
    returning * into v_request;
  return v_request;
end;
$$;
revoke all on function public.request_seller_withdrawal(bigint, text, text, text) from public, anon;
grant execute on function public.request_seller_withdrawal(bigint, text, text, text) to authenticated;

-- Product media paths are seller_id/product_id/object. Use the object path, not product.name.
drop policy if exists "sellers upload own product media" on storage.objects;
drop policy if exists "sellers manage own product media" on storage.objects;
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
