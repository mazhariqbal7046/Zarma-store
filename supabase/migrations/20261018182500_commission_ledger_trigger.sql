-- Record the platform commission from the final database price after checkout.
-- The trigger is SECURITY DEFINER so customers cannot write commission rows directly.
create unique index if not exists commission_records_order_seller_key
  on public.commission_records(order_id, seller_id)
  where seller_id is not null;

create schema if not exists private;
revoke all on schema private from public;

create or replace function private.record_item_commission()
returns trigger
language plpgsql
security definer
set search_path = public, private
as $$
declare
  v_seller_id uuid;
  v_gross bigint;
  v_commission bigint;
begin
  select p.seller_id into v_seller_id
  from public.order_items oi
  join public.product_variants pv on pv.id = oi.variant_id
  join public.products p on p.id = pv.product_id
  where oi.id = new.id;

  if v_seller_id is null then
    return new;
  end if;

  select coalesce(sum(oi.quantity::bigint * oi.unit_price_pkr::bigint), 0)
    into v_gross
  from public.order_items oi
  join public.product_variants pv on pv.id = oi.variant_id
  join public.products p on p.id = pv.product_id
  where oi.order_id = new.order_id and p.seller_id = v_seller_id;

  v_commission := round(v_gross * 0.12);

  insert into public.commission_records(order_id, seller_id, basis_pkr, rate, commission_pkr)
  values (new.order_id, v_seller_id, v_gross, 0.1200, v_commission)
  on conflict (order_id, seller_id) where seller_id is not null
  do update set basis_pkr = excluded.basis_pkr, commission_pkr = excluded.commission_pkr;

  insert into public.seller_earnings(seller_id, order_id, gross_pkr, commission_pkr, net_pkr)
  values (v_seller_id, new.order_id, v_gross, v_commission, v_gross - v_commission)
  on conflict (seller_id, order_id)
  do update set gross_pkr = excluded.gross_pkr,
                commission_pkr = excluded.commission_pkr,
                net_pkr = excluded.net_pkr;

  return new;
end;
$$;

drop trigger if exists order_item_commission_trigger on public.order_items;
create trigger order_item_commission_trigger
after insert on public.order_items
for each row execute function private.record_item_commission();

revoke all on function private.record_item_commission() from public, anon, authenticated;
