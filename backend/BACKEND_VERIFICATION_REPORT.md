# Zarma Store Backend Verification Report

Date: 2026-10-19 (Asia/Karachi), latest verification run

## Current policy recheck — 2026-10-20

- New platform policy: 10% commission for new eligible sales; historical commission rows are preserved.
- Backend calculation check: `PKR 10,000 -> PKR 1,000 platform commission, PKR 9,000 seller earnings`.
- Additive migration prepared: `supabase/migrations/20261020130000_set_platform_commission_10_percent.sql`.
- Local FastAPI restarted successfully; `/health`, `/docs`, `/openapi.json`, `/api/v1/products`, and `/api/v1/config` returned HTTP 200.
- Camera capture and protected seller/admin product creation are frontend features backed by existing authenticated APIs.
- The live try-on provider, payment providers, and remote migration application remain blocked by missing provider credentials/Supabase CLI authorization.

## Scope

Backend-only verification was performed in `C:\Users\khank\OneDrive\Desktop\Zarma Store`.
No files under `frontend/` or `n8n-workflows/` were modified.

## Python environment

- Installed interpreter detected: Python 3.14.5 only.
- Python 3.12/3.13 were not installed.
- `backend/requirements.txt` remains pinned.
- `py -m compileall -q app tests`: PASSED.
- Commission unit check: PASSED (`10000 -> 1200 commission, 8800 net`).
- Isolated `backend/.venv` was created successfully with Python 3.14.5.
- `pytest`/FastAPI imports: BLOCKED because package installation did not complete.
- PyPI access timed out; `pip index` returned no package versions in this environment.
- `winget` was attempted for Python 3.13 but its package lookup/install did not complete.
- No alternate Python 3.12/3.13 interpreter or cached compatible wheels were found.
- Repeatable launch script added: `backend/run_backend.ps1`.

## Network diagnosis (latest run)

Root cause: the current Codex execution context has an active outbound Windows Firewall/sandbox
restriction associated with `codex_sandbox_offline_block_outbound`, with `Direction=Outbound`,
`Action=Block`, `Profile=Any`, and all ports/protocols. This is the leading cause of the package
download failure. Its effective scope cannot be generalized to every Windows connection because
Supabase and OpenAI HTTPS connections from this context succeed; the evidence indicates selective
Codex egress/allowlisting. The rule was not disabled or modified because doing so would weaken
security controls.

Evidence collected:

- DNS: `pypi.org` and `files.pythonhosted.org` resolved successfully to Fastly IPv4 addresses.
- Routing: default route exists through `192.168.100.1`.
- ICMP: `pypi.org` responded successfully (45 ms).
- HTTPS/TCP: IPv4 and IPv6 requests to both PyPI hosts timed out; curl reported `HTTP=000`, exit
  code `28`, after 5 seconds. No HTTP `403`, `404`, `429`, TLS certificate error, or connection
  refusal was received.
- Endpoint comparison: Supabase and OpenAI HTTPS connections reached their servers and returned
  HTTP `401` without credentials, confirming that the local context has selective egress rather
  than a universal inability to make HTTPS connections.
- Proxy: no `HTTP_PROXY`, `HTTPS_PROXY`, or `ALL_PROXY` environment variables; WinHTTP reports
  direct access and Windows Internet Settings have proxy disabled.
- pip: no global, site, or user pip configuration files were present; the configured source was
  the official PyPI index.
- Firewall: the explicit outbound block rule above is enabled. No local override was attempted.
- Trusted PyPI metadata access through the authorized internet mechanism confirms the pinned
  FastAPI release exists; therefore the earlier `No matching distribution found` message was a
  consequence of index reachability, not evidence that the release is absent.

The local terminal cannot install packages while this sandbox firewall rule is active. The
authorized internet mechanism can inspect official metadata but cannot place wheel files into the
local virtual environment. No untrusted mirror, TLS bypass, or firewall bypass was used.

## FastAPI status

Status: BLOCKED BY DEPENDENCY INSTALLATION.

The ASGI entry point is `app.main:app`, but HTTP startup, `/health`, `/docs`, and `/openapi.json`
could not be run because FastAPI is not installed. No startup success is claimed.

## Supabase live status

Status: LIVE VERIFIED through the authorized Supabase MCP connection.

- Project: `orhpssosozwtwynlixgj`
- Project status: active/healthy
- REST catalog request: HTTP 200
- Public application tables: present
- RLS: enabled on application tables
- Private buckets verified: `tryon-private`, `product-media`, `product-3d`
- Applied migration history: 12 migrations, ending with `withdrawal_idempotency`
- Stored procedures verified: `create_order`, `adjust_inventory`, `cancel_order`,
  `request_seller_withdrawal`, and private commission trigger function

## Applied migrations

1. `initial_schema`
2. `commerce_backend_foundation`
3. `marketplace_ai_wallet_features`
4. `seller_admin_rls_policies`
5. `backend_storage_inventory`
6. `commission_ledger_trigger`
7. `backend_completion`
8. `backend_access_policies`
9. `financial_safety_functions`
10. `order_cancellation`
11. `backend_access_repairs`
12. `withdrawal_idempotency`
13. `tryon_uploads_and_lifecycle` (applied remotely as `20261019182207`)
14. `payments_wallet_safety_step6` (applied remotely as `20261019182808`)
15. `payment_event_index_cleanup` (applied remotely as `20261019183108`)

All changes were additive or access/function repairs. No destructive data operation was run.

## API endpoint status

Implemented in `app/api.py`:

- `/me`, `/me/custom-sizes`
- `/seller-applications`, `/admin/seller-applications`
- `/products`, `/products/{product_id}/reviews`
- `/seller/products`, variants, images, 3D assets, inventory
- `/wishlist`, `/reviews`
- `/cart`, `/cart/items`
- `/checkout`, `/orders`, `/orders/{order_id}/cancel`
- `/wallet`, `/seller/earnings`, `/seller/withdrawals`
- `/admin/customers`, `/admin/orders`, `/admin/transactions`, `/admin/withdrawals`, `/admin/analytics`
- `/ai/search`, `/ai/assistant`
- `/ai/try-on`, job status, signed result URL, deletion
- `/tryon/upload`, `/tryon/jobs`, `/tryon/jobs/{job_id}`, result, cancellation, upload deletion
- `/payments/initiate`, payment status, provider callbacks
- `/support/conversations`, messages
- `/notifications`

Classification: LOCAL CODE COMPILED; authenticated HTTP behavior remains UNVERIFIED until dependencies
and isolated test credentials are available.

## Latest automated run

- `py -m compileall -q app tests`: PASSED.
- `.venv` compile check: PASSED.
- Commission examples: PASSED.
- `pytest -q`: BLOCKED — `No module named pytest` in both available environments.
- FastAPI import/startup: PASSED with the system Python environment; `.venv` remains blocked because
  `fastapi`, `uvicorn`, and `pytest` are not installed there.
- Real local Uvicorn smoke test: PASSED — `/health` 200, `/docs` 200, `/openapi.json` 200.
- Try-on import/OpenAPI contract: PASSED — 54 paths loaded, including all new try-on routes.
- Live Supabase REST catalog check: PASSED — HTTP 200.
- `backend/run_backend.ps1`: NOT STARTED because FastAPI/Uvicorn are absent from `.venv`.
- The production `.venv` still needs dependencies before the documented backend launch command can
  be considered verified; the system-Python smoke server was stopped after verification.
- Step 2 smoke test file added at `tests/test_api_smoke.py`; execution remains blocked by the
  missing pytest package. Detailed Step 2 status is in `STEP2_FASTAPI_VERIFICATION_REPORT.md`.
- Step 3 test audit completed: 12 test functions are present, but pytest was blocked before
  collection by `No module named pytest`. Detailed results are in
  `STEP3_PYTEST_VERIFICATION_REPORT.md`.
- Step 4 AI work completed: official `google-genai` integration contract, deterministic catalog
  search, outfit recommendations, and owned conversation APIs were added. Live Gemini and HTTP
  verification remain blocked by the missing SDK/API key. Details are in
  `STEP4_GEMINI_AI_VERIFICATION_REPORT.md`.

## Security and database findings

- `notification_events` is intentionally internal-only: RLS is enabled with no client policies.
- Checkout and cancellation functions are `SECURITY DEFINER`, have fixed `search_path`, validate
  `auth.uid()`, and are restricted to authenticated execution. Supabase Advisor reports this as a
  warning because authenticated users can invoke these intended transaction entry points.
- Supabase Security Advisor reports no public RLS-disabled application tables.
- Performance Advisor reports unindexed foreign keys and multiple permissive policies. These are
  optimization findings, not data exposure findings; no broad policy removal was applied.
- Service-role keys are not present in source code or frontend files.

## Feature classification

- Seller/product/inventory/checkout/commission schema: LIVE VERIFIED at database level.
- 12% commission calculation: LOCAL TEST PASSED and trigger installed.
- Wallet withdrawal locking and seller-withdrawal idempotency: LIVE FUNCTION VERIFIED; real fund movement is not enabled.
- Gemini assistant: IMPLEMENTED BUT UNVERIFIED; deterministic catalog fallback is available.
- Virtual try-on: IMPLEMENTED BUT UNVERIFIED; live provider is disabled without credentials.
- Step 5 details: `STEP5_AI_VIRTUAL_TRYON_REPORT.md`.
- Step 6 financial/payment work: `STEP6_PAYMENTS_WALLET_REPORT.md`; core database safety is live
  verified, provider live/sandbox execution remains blocked by merchant credentials.
- JazzCash/Easypaisa: IMPLEMENTED CONTRACT ONLY; live provider behavior is BLOCKED by credentials
  and official merchant callback specifications.
- Support APIs: IMPLEMENTED BUT UNVERIFIED; authenticated/realtime end-to-end test not run.
- Step 7 live chat/notifications: database publication, RLS additions, RPCs, OpenAPI routes, and real FastAPI HTTP smoke are verified. Authenticated E2E remains blocked by missing isolated test users and `pytest`.
- 3D assets/storage metadata: LIVE SCHEMA VERIFIED; authenticated upload/access not exercised.

## Missing credentials/blockers

- `SUPABASE_SERVICE_ROLE_KEY`
- `GEMINI_API_KEY`
- `TRYON_PROVIDER_URL`
- `TRYON_PROVIDER_API_KEY`
- `JAZZCASH_MERCHANT_ID`, `JAZZCASH_PASSWORD`, `JAZZCASH_SHARED_SECRET`, and authorized sandbox account
- `EASYPAISA_MERCHANT_ID`, `EASYPAISA_CALLBACK_SECRET`, and the assigned official integration contract
- `JAZZCASH_MERCHANT_ID` and official callback/signature contract
- `EASYPAISA_MERCHANT_ID` and official callback/signature contract
- Compatible Python 3.12/3.13 or reachable package index for dependency installation
- Isolated Supabase test-user credentials for auth/RLS integration tests
- `SUPABASE_SERVICE_ROLE_KEY` for server-side notification delivery
- Codex execution environment network access approved for `pypi.org` and
  `files.pythonhosted.org`

## Production-readiness assessment

Not production-ready yet. Database structure, RLS baseline, transaction functions, and backend API
contracts are substantially implemented, but FastAPI runtime verification, automated pytest execution,
Gemini/try-on provider verification, payment-provider certification, and authenticated integration tests
remain outstanding.

## Step 7 live chat and notification verification

- Applied migration: `20261019183702_live_chat_notifications_step7`.
- Realtime publication verified for `support_tickets`, `conversations`, `messages`, and `notifications`.
- New support read/handoff/close and notification read RPCs verified live.
- Real Uvicorn smoke passed: `/health`, `/docs`, and `/openapi.json` returned HTTP 200.
- OpenAPI contract contains 67 paths, including the Step 7 support, admin, notification, and AI handoff routes.
- Full pytest remains blocked by missing `pytest`; no automated test count is claimed.
- Detailed Step 7 status: `backend/STEP7_LIVE_CHAT_NOTIFICATIONS_REPORT.md`.

## Step 8 security audit and protection verification

- Applied live migrations: `20261019184228_security_hardening_step8` and
  `20261019184430_security_hardening_step8_checkout`.
- Fixed profile role/account-status escalation, seller self-approval, inactive-seller access,
  support sender spoofing, payment callback/payment-attempt confusion, non-PKR callback acceptance,
  raw upstream error leakage, unsafe upload validation, search filter input, and missing sensitive-route
  rate limits.
- Checkout now rejects non-zero client-supplied discounts until a server-side coupon validation RPC is
  implemented. This closes discount manipulation without enabling unverified coupons.
- Live verification confirmed private storage buckets, RLS on the audited business tables, protected
  function privileges, payment-attempt binding, PKR callback checks, and the checkout discount guard.
- Local compile, OpenAPI import, real Uvicorn HTTP smoke, six Step 8 security contract checks, and three
  existing AI/provider/rate-limit contract checks passed.
- `python -m pytest -q` remains blocked before collection because `pytest` is not installed. No full
  pytest pass count is claimed.
- Security Advisor retains one intentional internal-only `notification_events` INFO finding and
  intentional authenticated `SECURITY DEFINER` transaction warnings. Performance Advisor retains
  foreign-key/index/policy optimization findings.
- Step 8 detailed report: `backend/STEP8_SECURITY_AUDIT_REPORT.md`.
- Production certification remains pending missing provider credentials, isolated auth test users,
  and a trusted package-install path for the full test environment.

## Step 9 full integration and end-to-end verification

- Fixed an outfit recommendation ranking regression: explicit query matches now outrank broad outfit
  candidates while real trousers/shoes/accessories can still be recommended from the catalog.
- Added live financial/storage hardening migrations:
  `20261019192302_step9_financial_storage_hardening` and
  `20261019192353_step9_storage_path_qualification_fix`.
- Removed direct authenticated writes to orders, order items, payments, and withdrawal requests;
  guarded RPCs are now the write path. Withdrawal RPC uses active-seller authorization, idempotency,
  fixed `search_path`, and row locking.
- Corrected seller storage ownership policy to use `storage.objects.name` explicitly for
  `seller_id/product_id/object` paths. Live policy text was re-queried after the fix.
- Python 3.13 is now installed, but the available project environments still lack pytest and the
  pinned test SDKs. System Python 3.14.5 was used for runtime verification.
- All 36 backend test functions were executed by a direct compatibility runner: 36 passed, 0 failed.
  This is not reported as pytest. `python -m pytest -q` remains blocked before collection with
  `No module named pytest`.
- With the live Supabase URL and publishable key in a temporary server process, real HTTP checks passed:
  `/health` 200, `/docs` 200, `/openapi.json` 200, `/api/v1/config` 200,
  `/api/v1/products` 200 with empty catalog, `/api/v1/ai/search` 200 with catalog fallback,
  and invalid bearer requests to `/api/v1/me` and `/api/v1/wallet` 401.
- Supabase live counts for audited customer/business tables remain zero; no disposable rows were added.
- Detailed Step 9 report: `backend/STEP9_FULL_INTEGRATION_TEST_REPORT.md`.
- Production certification remains pending authenticated isolated test users, pytest installation,
  service-role/Gemini/try-on/payment credentials, and provider sandbox access.

## Step 10 automatic deployment readiness

- No production deployment was performed because the full pytest suite remains blocked before
  collection (`No module named pytest`), so production traffic was not enabled.
- Local FastAPI smoke was rerun with system Python and a Render-compatible bind: `/health`,
  `/docs`, and `/openapi.json` each returned HTTP 200.
- `backend/run_backend.ps1` now uses `HOST`/`PORT` environment variables and defaults to
  `0.0.0.0:8000`; dependency-free JSON application logging was added without logging secrets.
- Render account access is available, but its workspace was not selected for this project. The
  project directory is not a Git repository and has no remote; no deployable Render manifest,
  Dockerfile, or Procfile is present.
- No live URL or HTTPS deployment result is claimed. Detailed status is in
  `backend/STEP10_DEPLOYMENT_REPORT.md`.

## Step 11 real AI and payment verification

- FastAPI local HTTP smoke remains verified: `/health`, `/docs`, and `/openapi.json` returned 200;
  `/api/v1/products` and `/api/v1/ai/search` returned 200 against the live empty catalog.
- Supabase project `orhpssosozwtwynlixgj` is `ACTIVE_HEALTHY`; audited tables remain RLS-enabled and
  no customer/test rows were added.
- Gemini is implemented with the official `google-genai` contract and deterministic fallback, but
  live testing is blocked by missing SDK/API key.
- Virtual try-on is implemented with private storage, signed URLs, job lifecycle, and provider
  adapter, but live generation is blocked by missing provider credentials and isolated test data.
- JazzCash local hash/callback contract is present; sandbox is blocked by merchant credentials.
  Easypaisa remains disabled pending its official merchant contract and credentials.
- Wallet/commission controls remain live-verified at the schema/function level; no real payment,
  withdrawal, refund settlement, or external fund transfer was performed.
- `python -m pytest -q` remains blocked before collection because `pytest` is not installed.
- Detailed Step 11 report: `backend/STEP11_REAL_AI_PAYMENT_REPORT.md`.

## Step 12 final production readiness audit

- Production launch is **NOT RECOMMENDED** yet: pytest is blocked before collection, provider and
  authenticated test credentials are missing, deployment is unavailable, and backup/recovery has
  not been drilled.
- Added safe request IDs, JSON application logs, aggregate metrics, protected `/metrics`, generic
  unhandled-error responses, and graceful Supabase HTTP client shutdown.
- Reused Supabase HTTP connections; warm live-catalog requests improved to approximately 200–249 ms
  after the initial connection setup.
- Live Supabase project, RLS, protected RPC grants, commission trigger, private buckets, advisors,
  and zero-row safety state were re-verified without data mutation.
- Manual contract runner: 37 passed, 0 failed; this is not a pytest result. `python -m pytest -q`
  remains blocked because `pytest` is not installed.
- Detailed Step 12 report: `backend/STEP12_PRODUCTION_READINESS_REPORT.md`.
