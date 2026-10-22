-- Additive AI try-on hardening. This migration does not delete or rewrite existing
-- customer data. Legacy queued/deleted enum values remain for compatibility.
alter type public.tryon_job_status add value if not exists 'pending';
alter type public.tryon_job_status add value if not exists 'cancelled';

create table if not exists public.tryon_uploads (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  storage_path text not null unique,
  mime_type text not null check (mime_type in ('image/jpeg', 'image/png', 'image/webp')),
  byte_size integer not null check (byte_size > 0 and byte_size <= 10485760),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  expires_at timestamptz not null default (now() + interval '24 hours'),
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, sha256)
);

alter table public.tryon_uploads enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'tryon_uploads'
      and policyname = 'users manage own tryon uploads'
  ) then
    create policy "users manage own tryon uploads"
      on public.tryon_uploads for all to authenticated
      using (user_id = (select auth.uid()))
      with check (user_id = (select auth.uid()));
  end if;
end $$;

create index if not exists tryon_uploads_user_created_idx
  on public.tryon_uploads(user_id, created_at desc);
create index if not exists tryon_uploads_expiry_idx
  on public.tryon_uploads(expires_at)
  where deleted_at is null;

comment on table public.tryon_uploads is
  'Private customer source images for AI try-on; storage objects are owned by user_id and expire.';
