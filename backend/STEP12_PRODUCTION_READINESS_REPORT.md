# Zarma Store — Step 12 Production Readiness, Security and Monitoring Report

Date: 2026-10-20
Scope: backend and Supabase only. Frontend and n8n were not modified.

## Executive decision

**NOT PRODUCTION READY / DO NOT LAUNCH CUSTOMER TRAFFIC YET.**

The backend and Supabase security baseline are substantially implemented and live-verified, but
production certification is blocked by missing pinned dependencies and pytest execution, missing
provider credentials, unavailable authenticated test accounts, no authorized deployment URL, and
unverified backup/recovery execution. Real payments, withdrawals, refunds, and customer traffic
were not activated.

## Feature classification

| Area | Status | Evidence / blocker |
|---|---|---|
| FastAPI startup and health | LIVE VERIFIED | Real Uvicorn HTTP smoke: `/health`, `/docs`, `/openapi.json` all 200. |
| Python environment | IMPLEMENTED BUT UNVERIFIED | Python 3.14.5 runtime works; Python 3.13 is installed; `backend/.venv` is incomplete. |
| Deployment | BLOCKED | Step 10 found no Git repository/remote, no live URL, and no confirmed Render workspace. |
| Authentication | LOCAL TEST PASSED | Missing/invalid bearer requests return 401; authenticated multi-user tests need isolated accounts. |
| Seller/product isolation | LIVE SCHEMA VERIFIED / IMPLEMENTED BUT UNVERIFIED | RLS and ownership policies are live; authenticated seller E2E was not run. |
| Checkout/inventory | LIVE FUNCTION VERIFIED / IMPLEMENTED BUT UNVERIFIED | Guarded checkout RPC and inventory schema are live; no disposable authenticated order fixture. |
| 12% commission | LIVE FUNCTION VERIFIED / LOCAL TEST PASSED | Trigger and logic verified; PKR 10,000 → PKR 1,200 commission / PKR 8,800 seller earnings. |
| Wallet/withdrawals | LIVE FUNCTION VERIFIED / LOCAL TEST PASSED | Locks/idempotency/RLS verified; no real withdrawal or settlement performed. |
| Gemini | IMPLEMENTED BUT UNVERIFIED | Official SDK contract and catalog fallback exist; SDK/API key missing. |
| Virtual try-on | IMPLEMENTED BUT UNVERIFIED / BLOCKED | Private storage/job/provider adapter exists; provider credentials and test image/user missing. |
| JazzCash | LOCAL TEST PASSED / SANDBOX BLOCKED | Hash/callback guards pass; merchant sandbox credentials unavailable. |
| Easypaisa | IMPLEMENTED BUT UNVERIFIED / BLOCKED | Disabled pending official merchant contract and credentials. |
| Live chat/realtime | DATABASE/LOCAL CONTRACT VERIFIED | Realtime publication/RLS and local contracts verified; two-user E2E blocked. |
| Monitoring | LOCAL TEST PASSED | Request IDs, structured safe logs, aggregate metrics, and graceful HTTP client shutdown added. |
| Backups/recovery | BLOCKED | Backup snapshot/plan status and restore drill were not available through authorized tools. |

## Production environment and process

- `backend/run_backend.ps1` binds to `HOST` (default `0.0.0.0`) and `PORT` (default `8000`).
- Application shutdown now closes the shared Supabase HTTP connection pool cleanly.
- The app is ASGI-compatible with Uvicorn. A multi-worker production configuration was not enabled:
  the current rate limiter and metrics are process-local and require Redis/API-gateway design before
  horizontal scaling.
- CORS uses explicit `FRONTEND_ORIGINS`; no wildcard origin is enabled.
- No `.env` or production secret values exist in the repository.
- No HTTPS deployment exists to verify; TLS must be terminated by the authorized host before launch.

## Monitoring and logging changes

Implemented in `app/logging_config.py` and `app/main.py`:

- UUID `X-Request-ID` response header on every request.
- JSON application logs containing request ID, method, route template, status, and duration.
- Aggregate counters for total requests, 4xx, 5xx, and average duration.
- Optional `/metrics` endpoint, hidden unless `METRICS_TOKEN` is configured and supplied via
  `X-Metrics-Token`.
- Unhandled exceptions return a generic 500 response and log only a safe exception type.
- `httpx`/`httpcore` INFO logging is suppressed so Supabase URLs, filters, bodies, and headers are
  not copied into application logs.
- Passwords, API keys, customer photos, payment payloads, and request bodies are not logged.

No external paid monitoring service was created or configured. Host-level uptime alerting and log
retention remain deployment responsibilities.

## Supabase production check

Live project: `orhpssosozwtwynlixgj`

- Project status: `ACTIVE_HEALTHY`.
- PostgreSQL 17.11; region `ap-south-1`.
- All audited business tables returned `rls_enabled=true`.
- Private buckets: `tryon-private`, `product-media`, `product-3d`.
- Protected functions use fixed `search_path=public` where applicable.
- `create_order` and admin withdrawal RPC are authenticated-only; payment event processing is not
  executable by `anon` or `authenticated`; old withdrawal overload is not executable by them.
- Commission trigger `order_item_commission_trigger` is present.
- Live catalog and audited customer/test counts remain zero; no test rows were created.
- Security Advisor: 1 intentional INFO (`notification_events` has no client policy) and 11 intended
  authenticated SECURITY DEFINER transaction warnings.
- Performance Advisor: 27 unindexed foreign-key INFO findings, 22 unused-index INFO findings, and
  42 multiple-permissive-policy WARN findings remain. These were not changed destructively.

## Backup and recovery

The authorized Supabase tools exposed project status, SQL inspection, migrations, advisors, and a
restore operation, but did not expose backup snapshot availability or the project billing plan.
The CLI supports private `supabase db dump`, but no database password/connection secret was available,
so no backup was created and no restore drill was attempted.

Required pre-launch recovery procedure:

1. Confirm the Supabase plan's automated backup/PITR retention in the project dashboard.
2. Create an encrypted private schema/data dump through an approved secret-managed CI job.
3. Restore that dump into an isolated non-production Supabase project or approved recovery target.
4. Verify migrations, RLS, functions, storage policies, and financial reconciliation before any cutover.

Do not upload a database dump to a public location or commit it to the repository.

## Performance results

Non-destructive local HTTP timing against the live empty Supabase catalog, three requests per endpoint:

| Endpoint | Status | Result |
|---|---:|---|
| `GET /api/v1/products` | 200 | Cold first request ~5365 ms; warm requests 204–216 ms. |
| `POST /api/v1/ai/search` | 200 | Warm requests 209–249 ms; deterministic fallback used. |

The first cold request includes network/TLS setup in this execution environment. Shared HTTP client
pooling reduced subsequent requests from roughly 4.2–6.0 seconds to roughly 0.2–0.25 seconds. This
is a smoke measurement, not a load test. No production data was stressed.

## Testing results

- Python compilation: **PASSED** (`compileall` for app and tests).
- Manual compatibility contract runner: **37 passed, 0 failed**. This includes the new request-ID /
  metrics contract, but it is explicitly not pytest.
- Real local HTTP smoke: **PASSED** for health/docs/OpenAPI/products/AI fallback and invalid-session
  rejection (`401` for `/api/v1/me` and `/api/v1/wallet`).
- Supabase live read-only checks: **PASSED** for project status, migrations, RLS, functions, trigger,
  grants, buckets, advisors, and zero-row safety checks.
- `python -m pytest -q`: **BLOCKED before collection** with `No module named pytest`.
- Authenticated seller/customer/admin, concurrent checkout/withdrawal, storage upload, realtime
  two-user delivery, Gemini live, try-on provider, JazzCash sandbox, Easypaisa sandbox, backup
  restore: **BLOCKED or UNVERIFIED**, not counted as passes.

## Remaining blockers

- Install pinned `requirements.txt` into `backend/.venv`, especially `pytest==8.3.4` and
  `google-genai==2.31.0`, through a trusted package source.
- Provide isolated Supabase customer, seller, and admin test accounts.
- Configure `GEMINI_API_KEY`, try-on provider credentials, and server-only Supabase service key.
- Complete JazzCash/Easypaisa merchant onboarding and official sandbox contract verification.
- Confirm Render workspace and attach an authorized Git deployment source; then verify HTTPS and logs.
- Confirm backup/PITR availability and complete an isolated restore drill.
- Move rate limiting/metrics to a shared production service before multi-instance scaling.

## Production recommendation

Keep production traffic disabled. The current backend is suitable for continued local/staging
hardening, not a customer-facing launch. Reassess only after pytest executes, authenticated E2E
security tests pass, provider sandbox responses are verified, deployment HTTPS is tested, and backup
recovery is demonstrated.
