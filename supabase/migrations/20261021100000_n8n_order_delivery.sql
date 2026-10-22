-- Persistent idempotency and retry state for signed n8n order notifications.
create table if not exists public.n8n_order_deliveries (
  event_id text primary key,
  order_id uuid not null unique references public.orders(id) on delete cascade,
  status text not null default 'pending' check (status in ('pending', 'delivered')),
  attempts integer not null default 0 check (attempts >= 0),
  last_error text,
  delivered_at timestamptz,
  created_at timestamptz not null default now()
);

alter table public.n8n_order_deliveries enable row level security;
revoke all on public.n8n_order_deliveries from anon, authenticated;

create or replace function public.claim_n8n_order_notification(p_order_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid := auth.uid();
  v_status text;
begin
  if v_user_id is null or not exists (select 1 from public.orders where id = p_order_id and user_id = v_user_id) then
    raise exception 'Order access denied';
  end if;
  insert into public.n8n_order_deliveries(event_id, order_id)
  values ('order.created:' || p_order_id::text, p_order_id)
  on conflict (event_id) do nothing;
  select status into v_status from public.n8n_order_deliveries where order_id = p_order_id for update;
  if v_status = 'delivered' then return false; end if;
  update public.n8n_order_deliveries set attempts = attempts + 1, last_error = null where order_id = p_order_id;
  return true;
end;
$$;

create or replace function public.complete_n8n_order_notification(p_order_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.uid() is null or not exists (select 1 from public.orders where id = p_order_id and user_id = auth.uid()) then
    raise exception 'Order access denied';
  end if;
  update public.n8n_order_deliveries
    set status = 'delivered', delivered_at = now(), last_error = null
    where order_id = p_order_id;
end;
$$;

revoke all on function public.claim_n8n_order_notification(uuid) from public, anon;
revoke all on function public.complete_n8n_order_notification(uuid) from public, anon;
grant execute on function public.claim_n8n_order_notification(uuid) to authenticated;
grant execute on function public.complete_n8n_order_notification(uuid) to authenticated;
