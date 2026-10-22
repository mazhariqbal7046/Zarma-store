create or replace function public.cancel_order(p_order_id uuid)
returns public.orders
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_order public.orders;
  v_item record;
begin
  select * into v_order from public.orders where id = p_order_id and user_id = (select auth.uid()) for update;
  if not found then raise exception 'Order not found'; end if;
  if v_order.status not in ('pending', 'confirmed') then raise exception 'Order cannot be cancelled in its current state'; end if;
  for v_item in select variant_id, quantity from public.order_items where order_id = p_order_id loop
    update public.inventory set reserved_quantity = reserved_quantity - v_item.quantity, updated_at = now()
      where variant_id = v_item.variant_id and reserved_quantity >= v_item.quantity;
    if not found then raise exception 'Inventory reservation is inconsistent'; end if;
  end loop;
  update public.orders set status = 'cancelled' where id = p_order_id returning * into v_order;
  return v_order;
end;
$$;

revoke execute on function public.cancel_order(uuid) from public, anon;
grant execute on function public.cancel_order(uuid) to authenticated;
