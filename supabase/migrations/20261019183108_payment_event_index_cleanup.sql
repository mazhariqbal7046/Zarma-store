-- The original backend_completion migration already created the equivalent
-- unique constraint index. Keep that canonical index and remove only the
-- redundant index introduced by the Step 6 migration.
drop index if exists public.payment_events_provider_event_key;
