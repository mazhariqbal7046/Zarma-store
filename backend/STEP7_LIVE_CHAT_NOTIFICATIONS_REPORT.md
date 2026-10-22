# Step 7 — Live Chat, AI-to-Human Support, and Notifications

Date: 2026-10-19  
Scope: backend and Supabase only. Frontend and n8n were not modified.

## Implemented

- Customer support conversation creation, listing, detail, messages, close, and read-state APIs.
- Admin support inbox alias, ticket status/priority/assignment update, and admin message delivery.
- AI-to-human handoff from an authenticated AI conversation, including a bounded recent-message context and a support ticket.
- Explicit handoff endpoint for an existing support conversation, with deterministic AI response `handoff_suggested` when a customer asks for a human.
- Notification creation for new tickets, customer messages, admin replies, and handoffs.
- Notification listing, unread count, mark-one-read, and mark-all-read APIs.
- Notification delivery is server-only, idempotent through `dedupe_key`, and degrades safely when the service-role credential is absent.
- Safe RPCs for read state, handoff, closing conversations, and notification read state. All use fixed `search_path`, validate `auth.uid()`, and restrict execution to `authenticated`.
- Supabase Realtime Postgres Changes publication for `support_tickets`, `conversations`, `messages`, and `notifications`. Existing RLS select policies continue to authorize row delivery.

## API endpoints

- `POST /api/v1/support/conversations`
- `GET /api/v1/support/conversations`
- `GET /api/v1/admin/support/conversations`
- `GET /api/v1/support/conversations/{conversation_id}`
- `POST /api/v1/support/conversations/{conversation_id}/messages`
- `POST /api/v1/support/conversations/{conversation_id}/read`
- `POST /api/v1/support/conversations/{conversation_id}/handoff`
- `POST /api/v1/support/conversations/{conversation_id}/close`
- `PATCH /api/v1/admin/support/conversations/{conversation_id}`
- `GET /api/v1/notifications`
- `GET /api/v1/notifications/unread-count`
- `POST /api/v1/notifications/{notification_id}/read`
- `POST /api/v1/notifications/read-all`
- `POST /api/v1/ai/conversations/{conversation_id}/handoff`
- Existing `POST /api/v1/ai/chat` and `/api/v1/ai/assistant` now return `handoff_suggested` without changing existing response fields.

## Database status

Local migration: `supabase/migrations/20261019183346_live_chat_notifications_step7.sql`  
Applied live by Supabase as: `20261019183702_live_chat_notifications_step7`

Verified live:

- `messages.read_at`
- `conversations.handoff_reason`, `handoff_at`, `ai_context`, `last_read_at`
- `notifications.dedupe_key` and unique per-user dedupe index
- Admin select/update policies for `support_tickets`
- RPCs: `mark_conversation_read`, `request_human_handoff`, `close_support_conversation`, `mark_notification_read`, `mark_all_notifications_read`
- Realtime publication includes all four support/notification tables
- No existing data was deleted or rewritten.

## Security and limitations

- `notification_events` remains RLS-protected and internal-only; it was not exposed to clients.
- Supabase Security Advisor reports the expected warning for authenticated execution of protected `SECURITY DEFINER` RPCs. These functions have fixed `search_path`, explicit auth/ownership checks, and only authenticated execute grants.
- Notification delivery requires `SUPABASE_SERVICE_ROLE_KEY` on the backend. It is not committed, returned by any API, or safe for frontend use.
- Realtime client subscription code belongs to the existing frontend and was intentionally not changed. The database publication and RLS authorization are live.

## Verification

- Python compilation: **PASSED** — `python -m compileall -q app tests`.
- OpenAPI contract: **PASSED** — 67 paths, all Step 7 routes present.
- Real Uvicorn HTTP smoke: **PASSED** — `/health`, `/docs`, `/openapi.json` returned HTTP 200.
- Local Step 7 behavior contracts: **PASSED** — payload validation, route contract, and no-service-role notification fallback.
- Live Supabase migration, columns, policies, RPCs, and Realtime publication: **PASSED**.
- Full pytest: **BLOCKED** — `pytest` is not installed in the available Python 3.14 environments; official PyPI access is blocked by the execution environment. No test pass count is fabricated.
- Authenticated customer/admin chat E2E: **NOT RUN** — no isolated test-user credentials were available and no real customer data was touched.

## Remaining blockers

- Install a compatible test dependency set (`pytest`, preferably in the project `.venv`) through an approved reachable package source.
- Provide `SUPABASE_SERVICE_ROLE_KEY` only through the protected backend runtime environment to enable notification delivery.
- Provide isolated Supabase customer/admin test accounts for authenticated RLS and Realtime end-to-end tests.
- Frontend must subscribe to private/authenticated Postgres Changes channels when the frontend phase is authorized; no frontend work was performed in Step 7.
