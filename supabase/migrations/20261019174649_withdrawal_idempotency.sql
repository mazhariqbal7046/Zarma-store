alter table public.withdrawal_requests add column if not exists idempotency_key text;
create unique index if not exists withdrawal_requests_seller_idempotency_key
  on public.withdrawal_requests(seller_id, idempotency_key)
  where idempotency_key is not null;

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
  select coalesce(sum(net_pkr) filter (where status = 'available'), 0) into v_available from public.seller_earnings where seller_id = v_seller_id;
  select coalesce(sum(amount_pkr), 0) into v_locked from public.withdrawal_requests where seller_id = v_seller_id and status in ('pending', 'approved');
  if p_amount_pkr > v_available - v_locked then raise exception 'Insufficient available seller balance'; end if;
  insert into public.withdrawal_requests(seller_id, amount_pkr, payout_method, payout_reference, idempotency_key)
    values (v_seller_id, p_amount_pkr, p_payout_method, p_payout_reference, p_idempotency_key)
    returning * into v_request;
  return v_request;
end; $$;

revoke execute on function public.request_seller_withdrawal(bigint, text, text, text) from public, anon;
grant execute on function public.request_seller_withdrawal(bigint, text, text, text) to authenticated;
revoke execute on function public.request_seller_withdrawal(bigint, text, text) from authenticated;
