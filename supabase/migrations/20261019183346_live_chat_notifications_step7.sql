-- Step 7: live support chat, AI-to-human handoff, notifications, and Realtime.
-- Additive only: no existing rows are deleted or rewritten.

begin;

alter table public.conversations
  add column if not exists handoff_reason text,
  add column if not exists handoff_at timestamptz,
  add column if not exists ai_context jsonb not null default '{}'::jsonb,
  add column if not exists last_read_at timestamptz;

alter table public.messages
  add column if not exists read_at timestamptz;

alter table public.notifications
  add column if not exists dedupe_key text;

create index if not exists conversations_user_created_idx
  on public.conversations(user_id, created_at desc);
create index if not exists conversations_ticket_idx
  on public.conversations(support_ticket_id);
create index if not exists messages_conversation_created_idx
  on public.messages(conversation_id, created_at asc);
create index if not exists messages_conversation_unread_idx
  on public.messages(conversation_id, read_at)
  where read_at is null;
create index if not exists support_tickets_status_updated_idx
  on public.support_tickets(status, updated_at desc);
create unique index if not exists notifications_user_dedupe_idx
  on public.notifications(user_id, dedupe_key)
  where dedupe_key is not null;

-- Admin support inbox access was intentionally absent from the original ticket policies.
do $$
begin
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'support_tickets' and policyname = 'admins read all support tickets') then
    create policy "admins read all support tickets" on public.support_tickets
      for select to authenticated
      using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'support_tickets' and policyname = 'admins update support tickets') then
    create policy "admins update support tickets" on public.support_tickets
      for update to authenticated
      using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))
      with check (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
  end if;
end
$$;

create or replace function public.mark_conversation_read(p_conversation_id uuid)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  v_count integer := 0;
begin
  if not exists (
    select 1
    from public.conversations c
    where c.id = p_conversation_id
      and (c.user_id = (select auth.uid()) or exists (
        select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'
      ))
  ) then
    raise exception 'Conversation not found or not accessible';
  end if;

  update public.messages
  set read_at = coalesce(read_at, now())
  where conversation_id = p_conversation_id
    and read_at is null
    and sender_id is distinct from (select auth.uid());
  get diagnostics v_count = row_count;

  update public.conversations
  set last_read_at = now()
  where id = p_conversation_id;
  return v_count;
end;
$$;

create or replace function public.request_human_handoff(
  p_conversation_id uuid,
  p_reason text,
  p_ai_context jsonb default '{}'::jsonb
)
returns public.conversations
language plpgsql
security definer
set search_path = public
as $$
declare
  v_conversation public.conversations;
begin
  update public.conversations c
  set handoff_requested = true,
      handoff_reason = left(coalesce(p_reason, 'Customer requested human support'), 1000),
      handoff_at = coalesce(c.handoff_at, now()),
      ai_context = case when jsonb_typeof(coalesce(p_ai_context, '{}'::jsonb)) = 'object' then coalesce(p_ai_context, '{}'::jsonb) else '{}'::jsonb end
  where c.id = p_conversation_id
    and c.user_id = (select auth.uid())
  returning c.* into v_conversation;

  if v_conversation.id is null then
    raise exception 'Conversation not found or not owned by current user';
  end if;

  update public.support_tickets
  set status = 'pending', updated_at = now()
  where id = v_conversation.support_ticket_id;
  return v_conversation;
end;
$$;

create or replace function public.close_support_conversation(p_conversation_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_ticket_id uuid;
  v_allowed boolean := false;
begin
  select c.support_ticket_id into v_ticket_id
  from public.conversations c
  where c.id = p_conversation_id
    and (c.user_id = (select auth.uid()) or exists (
      select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'
    ));
  v_allowed := v_ticket_id is not null;
  if not v_allowed then
    raise exception 'Conversation not found or not accessible';
  end if;

  update public.support_tickets set status = 'closed', updated_at = now() where id = v_ticket_id;
  return true;
end;
$$;

create or replace function public.mark_notification_read(p_notification_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.notifications
  set read_at = coalesce(read_at, now())
  where id = p_notification_id and user_id = (select auth.uid());
  return found;
end;
$$;

create or replace function public.mark_all_notifications_read()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  v_count integer := 0;
begin
  update public.notifications
  set read_at = coalesce(read_at, now())
  where user_id = (select auth.uid()) and read_at is null;
  get diagnostics v_count = row_count;
  return v_count;
end;
$$;

revoke execute on function public.mark_conversation_read(uuid) from public, anon;
revoke execute on function public.request_human_handoff(uuid, text, jsonb) from public, anon;
revoke execute on function public.close_support_conversation(uuid) from public, anon;
revoke execute on function public.mark_notification_read(uuid) from public, anon;
revoke execute on function public.mark_all_notifications_read() from public, anon;
grant execute on function public.mark_conversation_read(uuid) to authenticated;
grant execute on function public.request_human_handoff(uuid, text, jsonb) to authenticated;
grant execute on function public.close_support_conversation(uuid) to authenticated;
grant execute on function public.mark_notification_read(uuid) to authenticated;
grant execute on function public.mark_all_notifications_read() to authenticated;

-- Enable Postgres Changes for the existing RLS-protected support surfaces.
do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'support_tickets') then
      alter publication supabase_realtime add table public.support_tickets;
    end if;
    if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'conversations') then
      alter publication supabase_realtime add table public.conversations;
    end if;
    if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'messages') then
      alter publication supabase_realtime add table public.messages;
    end if;
    if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'notifications') then
      alter publication supabase_realtime add table public.notifications;
    end if;
  end if;
end
$$;

commit;
