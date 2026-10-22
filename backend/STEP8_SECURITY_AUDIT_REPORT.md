# Step 8 — Backend Security Audit and Automatic Protection

Date: 2026-10-20  
Scope: FastAPI backend and Supabase only. Frontend and n8n were not modified.

## Executive status

Security hardening is implemented and live in Supabase, but the backend is **not certified production-secure yet**. The local FastAPI process starts and real unauthenticated HTTP smoke checks pass. Full pytest and authenticated RLS/payment/provider end-to-end checks remain blocked by missing local pytest/dependency setup, isolated test users, and provider credentials.

## Findings and fixes

### High severity findings fixed

- Profile authorization fields were protected. A customer can no longer change `role` or `account_status` through the profile update policy; a fixed-search-path trigger rejects privilege escalation.
- Seller applications no longer use a user-side `FOR ALL` policy. Customers can create pending applications and read their own applications, while approval/rejection remains admin-only.
- Inactive sellers no longer retain direct RLS access to seller products, variants, images, inventory, discounts, shops, or 3D assets.
- Customer message inserts now require the authenticated user to be the conversation owner and force `sender_type=customer` and `sender_id=auth.uid()`.
- Payment callbacks are bound to the intended payment attempt using the server-created provider transaction reference. Currency is restricted to PKR, callback replay protection remains enabled, and the provider event RPC is service-role-only.
- Client-controlled checkout discounts are rejected unless a server-side coupon validation flow exists. This prevents a customer from reducing an order total by submitting an arbitrary discount amount.

### Medium/defense-in-depth fixes

- Supabase upstream error bodies are retained only internally; API responses expose sanitized error messages.
- Public search input is length-limited and filter metacharacters are removed before query construction.
- Product image, try-on image, and 3D uploads have bounded reads and content/magic validation. Product media and try-on buckets are private.
- Sensitive support, AI, checkout, payment, refund, withdrawal, and upload routes have per-user/provider in-process rate limits.
- The backend profile authentication lookup now rejects suspended/closed accounts before role-based authorization.
- `backend/.gitignore` excludes `.env`, virtual environments, caches, and logs. A secret scan found no real Supabase service key, Gemini key, JWT, or payment secret in backend source.

## Live Supabase verification

- Project: `orhpssosozwtwynlixgj`.
- Applied migrations include `security_hardening_step8` and `security_hardening_step8_checkout` (remote versions `20261019184228` and `20261019184430`).
- `profiles`, seller application, seller catalog, order/payment, wallet/withdrawal, support, notification, try-on, and AI tables retain RLS enabled.
- Buckets `tryon-private`, `product-media`, and `product-3d` exist and are private.
- Live function checks confirmed:
  - `create_order`: anonymous execution denied; authenticated execution allowed; server-side discount guard present.
  - `process_payment_event`: anonymous and authenticated execution denied; service-role execution allowed; provider binding and PKR currency guard present.
  - `begin_payment_attempt`: anonymous execution denied; authenticated execution allowed; provider transaction binding present.
- Security Advisor still reports one intentional INFO finding for internal-only `notification_events` (RLS enabled with no client policies) and WARN findings for intended authenticated `SECURITY DEFINER` transaction entry points. These warnings were not ignored; the functions use authorization checks/fixed search paths and are documented as intentional.
- Performance Advisor still reports unindexed foreign keys, unused indexes, and multiple permissive policies. These are optimization items and were not changed destructively during this security audit.
- No customer/business rows were deleted or modified by the hardening migrations.

## Local verification

- Python: system Python 3.14.5.
- `python -m compileall -q backend/app backend/tests`: PASSED.
- FastAPI import/OpenAPI generation: PASSED; 67 routes loaded.
- Real Uvicorn HTTP smoke: PASSED — `/health`, `/docs`, and `/openapi.json` each returned HTTP 200. Server was stopped after the check.
- Focused Step 8 contract checks: PASSED — 6 checks executed directly with Python.
- Existing provider/AI/rate-limit contract checks: PASSED — 3 checks executed directly with Python.
- `python -m pytest -q`: BLOCKED before collection because `pytest` is not installed in the available Python environment. No pytest pass count is claimed.
- Authenticated RLS isolation, concurrent checkout, wallet double-spend, and real payment callback tests were not claimed because isolated test users and trusted server credentials are not configured.

## Security controls reviewed

- Auth/session: Supabase Auth validates the bearer session upstream; the API retrieves the user profile and enforces active account state and role. Session revocation behavior still depends on Supabase Auth configuration and was not tested with real users.
- RLS/authorization: seller ownership and admin-only operations are enforced by live policies and protected columns/triggers.
- Commerce/finance: database transaction functions, stock locking, idempotency, wallet ledger controls, commission logic, refund/withdrawal safeguards, and PKR validation remain in place. No live money movement is enabled.
- AI: catalog-grounded responses and deterministic fallback are available; prompts treat user/catalog/history as untrusted and do not grant the model order, wallet, price, or tool execution authority.
- Storage: private buckets, ownership checks, signed access, upload size limits, expiration/deletion paths, and content validation are present.
- API abuse: bounded Pydantic fields and file reads plus route rate limits are present. The current limiter is process-local; it must be moved to Redis/API gateway storage for multi-instance production deployment.

## Missing credentials and blockers

- `SUPABASE_SERVICE_ROLE_KEY` for trusted server-side callbacks, notifications, workers, and admin operations.
- `GEMINI_API_KEY` for live Gemini calls; deterministic catalog fallback remains available.
- Try-on provider URL/API key for live image generation.
- JazzCash merchant ID/password/shared secret and approved sandbox/live callback contract.
- Easypaisa merchant credentials, callback secret, and verified assigned API contract.
- Reachable trusted PyPI/package source or compatible environment for installing pytest and the pinned requirements into `backend/.venv`.
- Isolated Supabase test accounts/credentials for authenticated RLS and concurrency tests.

## Remaining recommended work

1. Implement a server-side coupon validation/redemption RPC, then allow only validated coupon IDs/claims in checkout.
2. Replace the in-process rate limiter with Redis or an API gateway limiter before horizontal scaling.
3. Add covering indexes for high-volume foreign keys after observing real query traffic.
4. Run authenticated integration and provider sandbox tests after credentials are supplied; do not use real customer data.

## Final assessment

**Step 8 security protections: implemented and live.**  
**Production security certification: pending** due to blocked pytest installation, missing isolated auth test users, and unavailable Gemini/try-on/payment credentials.
