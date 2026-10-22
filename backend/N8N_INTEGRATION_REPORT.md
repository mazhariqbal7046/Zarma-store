# Zarma Store n8n Cloud Integration Report

Date: 2026-10-21 (Asia/Karachi)

## Implemented

- Added `app/n8n_webhooks.py` for signed order notifications.
- Checkout calls n8n only after the Supabase `create_order` RPC returns a saved order.
- Payloads contain a stable `event_id` (`order.created:<order_id>`), event type, order totals/status, user ID, and validated item identifiers/quantities. Access tokens and payment secrets are never sent.
- Requests use HTTPS, `X-Zarma-Signature` HMAC-SHA256, `X-Zarma-Event-Id`, and `X-Zarma-Webhook-Secret` headers.
- Transient 5xx/network failures retry up to three times with backoff; 4xx responses are not retried.
- Added bounded process-local deduplication plus persistent Supabase claim/complete RPC migration for cross-process idempotency.
- Added import-ready `n8n-workflows/new-order-secure.json` with Header Auth and SMTP placeholders.
- Added import-ready workflows for customer welcome, verified payment confirmation, inventory alerts, order tracking, AI support bridge, and the 20:00 Asia/Karachi daily sales report.
- Added the verified signup path: frontend Supabase signup with an active session calls `POST /api/v1/auth/customer-registered`; the backend signs and forwards the event to the configured n8n customer-registration webhook.
- Existing legacy `n8n-workflows/new-order.json` was preserved.

## Configuration

Set these only in the backend host secret environment, never in frontend code:

```text
N8N_ORDER_WEBHOOK_URL=https://<your-n8n-host>/webhook/zarma/new-order
N8N_CUSTOMER_REGISTERED_WEBHOOK_URL=https://<your-n8n-host>/webhook-test/<customer-registration-id>
N8N_WEBHOOK_SECRET=<long-random-secret>
```

In n8n, import `new-order-secure.json`, configure Header Auth credential `Zarma webhook secret` with header `X-Zarma-Webhook-Secret`, configure the SMTP credential, and set `ORDER_FROM_EMAIL` / `ORDER_MANAGER_EMAIL`.

## Verification

- `pytest`: 42 passed, 0 failed.
- Python compilation: passed.
- Workflow JSON syntax: valid.
- All eight JSON exports in `n8n-workflows/` parse successfully.
- FastAPI `/health`: HTTP 200.
- Mock webhook tests cover HMAC event delivery, duplicate suppression, and transient retry.

## Live status

The customer-registration URL supplied by the user is now configured locally, but `N8N_WEBHOOK_SECRET` is intentionally still empty. Therefore the backend will not transmit signup data yet. The n8n Cloud workflow could not be inspected or activated because this session has no authenticated n8n control/API access. No real customer order, payment, or signup was sent. The integration is **not live-verified**.

Before enabling the workflow, apply `supabase/migrations/20261021100000_n8n_order_delivery.sql` through the authorized Supabase migration path and perform one disposable authenticated test order in a non-production/test environment.
