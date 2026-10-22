-- Checkout runs in one transaction, re-checks prices from the database, and reserves stock.
alter table public.shopping_carts add constraint shopping_carts_user_status_key unique (user_id, status);

create policy "customers can create orders" on public.orders for insert to authenticated
with check ((select auth.uid()) = user_id);
create policy "customers can create order items" on public.order_items for insert to authenticated
with check (exists (select 1 from public.orders o where o.id = order_id and o.user_id = (select auth.uid())));
create policy "customers can create payments" on public.payments for insert to authenticated
with check (exists (select 1 from public.orders o where o.id = order_id and o.user_id = (select auth.uid())));

create or replace function public.create_order(
  p_idempotency_key text,
  p_address_id uuid,
  p_items jsonb,
  p_delivery_pkr integer default 0,
  p_discount_pkr integer default 0
)
returns public.orders
language plpgsql
security invoker
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
begin
  if v_user_id is null then raise exception 'Authentication required'; end if;
  if p_idempotency_key is null or length(trim(p_idempotency_key)) < 8 then raise exception 'Invalid idempotency key'; end if;
  if not exists (select 1 from public.addresses where id = p_address_id and user_id = v_user_id) then raise exception 'Invalid address'; end if;

  select * into v_order from public.orders where idempotency_key = p_idempotency_key and user_id = v_user_id;
  if found then return v_order; end if;
  if jsonb_array_length(p_items) = 0 then raise exception 'Cart is empty'; end if;

  for v_item in select * from jsonb_array_elements(p_items) loop
    v_quantity := (v_item->>'quantity')::integer;
    select * into v_variant from public.product_variants where id = (v_item->>'variant_id')::uuid;
    if not found or v_quantity < 1 then raise exception 'Invalid product variant'; end if;
    select * into v_product from public.products where id = v_variant.product_id and active = true;
    if not found then raise exception 'Product is unavailable'; end if;
    select * into v_inventory from public.inventory where variant_id = v_variant.id for update;
    if not found or v_inventory.quantity - v_inventory.reserved_quantity < v_quantity then raise exception 'Insufficient stock for %', v_product.name; end if;
    v_unit_price := coalesce(v_variant.price_pkr, v_product.price_pkr);
    v_subtotal := v_subtotal + (v_unit_price * v_quantity);
  end loop;

  insert into public.orders (user_id, address_id, subtotal_pkr, delivery_pkr, discount_pkr, idempotency_key)
  values (v_user_id, p_address_id, v_subtotal, greatest(p_delivery_pkr, 0), greatest(p_discount_pkr, 0), p_idempotency_key)
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

revoke execute on function public.create_order(text, uuid, jsonb, integer, integer) from public, anon;
grant execute on function public.create_order(text, uuid, jsonb, integer, integer) to authenticated;
