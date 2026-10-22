# Zarma Store — Step 11 Real AI, Virtual Try-On and Payment Report

Date: 2026-10-20
Scope: backend only. Frontend and n8n were not modified.

## Status summary

| Area | Status | Evidence |
|---|---|---|
| FastAPI local runtime | LIVE VERIFIED | Real local Uvicorn smoke returned 200 for `/health`, `/docs`, and `/openapi.json`. |
| Deployment | BLOCKED | Step 10 was not deployed: no Git remote/repository and no confirmed Render workspace. |
| Supabase project | LIVE VERIFIED | Project `orhpssosozwtwynlixgj` reported `ACTIVE_HEALTHY`; current schema and migrations were queried. |
| Gemini integration | IMPLEMENTED BUT UNVERIFIED | Official `google-genai` integration exists, but SDK and `GEMINI_API_KEY` are absent. |
| AI catalog search | LOCAL TEST PASSED / FALLBACK VERIFIED | Live Supabase catalog query returned 200 with zero products; deterministic catalog fallback was used. |
| Virtual try-on | IMPLEMENTED BUT UNVERIFIED / BLOCKED | Private storage, signed URLs, jobs, worker, and provider adapter exist; provider URL/key and test user/image are missing. |
| JazzCash | LOCAL CONTRACT PASSED / SANDBOX BLOCKED | Hash and callback guards exist; current callback returned 503 because merchant configuration is absent. |
| Easypaisa | IMPLEMENTED BUT UNVERIFIED / BLOCKED | Disabled until the assigned merchant contract and credentials are verified. |
| Wallet and ledger | LIVE SCHEMA VERIFIED / LOCAL TEST PASSED | Atomic ledger/RPC design and RLS are live; no real withdrawal or settlement was performed. |
| 12% commission | LOCAL TEST PASSED / LIVE FUNCTION VERIFIED | PKR 10,000 produces PKR 1,200 commission and PKR 8,800 seller earnings. |
| Automated pytest | BLOCKED | `python -m pytest -q` stops before collection with `No module named pytest`. |

## FastAPI and deployment

The backend is not continuously running after verification. A real local process was started on
`127.0.0.1:8788` with publishable Supabase configuration and then stopped safely.

Verified HTTP results:

- `GET /health` → 200
- `GET /docs` → 200
- `GET /openapi.json` → 200
- `GET /api/v1/products` → 200; live catalog currently empty
- `POST /api/v1/ai/search` → 200; deterministic fallback with empty catalog
- malformed/unauthorized protected requests remain rejected by validation/authentication
- `POST /api/v1/payments/jazzcash/callback` → 503 because merchant configuration is absent
- unauthenticated `POST /api/v1/tryon/jobs` → 401

No production URL, HTTPS result, payment collection, payout, or deployment success is claimed.

## Gemini AI

The backend uses the official `google-genai` SDK contract, optional at import time, with a strict
catalog-grounded fallback. Gemini is never allowed to invent products, prices, stock, order status,
or perform mutations. Search intent is validated against allowlisted fields and conversation data
is user-scoped.

The current environment has neither `google-genai` nor `GEMINI_API_KEY`, so no real Gemini request
was attempted and no live provider response is claimed. The configured model remains deployment
configurable through `GEMINI_MODEL`; a production deployment should select a currently supported
stable model after credentials are supplied.

Official references reviewed:

- [Google GenAI SDK](https://ai.google.dev/gemini-api/docs/libraries)
- [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models)

## Virtual try-on

Implemented backend capabilities:

- private customer source uploads in `tryon-private`
- MIME, magic-byte, size, and image-dimension validation
- customer-owned job and upload authorization
- asynchronous provider submission/polling worker contract
- provider-host SSRF protection
- private result storage and short-lived signed URLs
- deletion, cancellation, expiry metadata, and provider failure handling

Live generation is **BLOCKED**. `TRYON_PROVIDER_URL`, `TRYON_PROVIDER_API_KEY`,
`SUPABASE_SERVICE_ROLE_KEY`, an isolated test user, consented test image, and an active product
image are required. No mock image is returned as a real result.

## JazzCash and Easypaisa

JazzCash local contract work includes PKR checkout fields, SHA-256 secure-hash construction,
signature verification, callback replay protection through the database event path, and provider
configuration guards. A callback without merchant configuration correctly returned HTTP 503. No
sandbox transaction was submitted.

Easypaisa remains disabled until the merchant-specific official contract is supplied and verified;
its signature format is not assumed to match JazzCash. No sandbox request, refund, or settlement was
performed.

Official references reviewed:

- [JazzCash merchant sandbox integration guide](https://sandbox.jazzcash.com.pk/SandboxDocumentation/Content/documentation/Payment%20Gateway%20Integration%20Guide%20for%20Merchants-v4.2.pdf)
- [Easypaisa payment integration guides](https://easypay.easypaisa.com.pk/easypay-merchant/faces/pg/site/IntegrationGuides.jsf)

## Wallet, financial safety and commission

- Wallets, wallet transactions, seller earnings, commission records, withdrawals, payment attempts,
  refunds, and payment events exist in the live Supabase schema with RLS enabled.
- Financial writes use guarded database functions, idempotency keys, and row locks where required.
- Direct authenticated writes to sensitive financial tables were revoked in Step 9.
- No customer payment, withdrawal, refund settlement, or external fund movement was attempted.
- The commission rate remains exactly 12% of the eligible selling price. Example: PKR 10,000 →
  PKR 1,200 platform commission and PKR 8,800 seller earnings before other fees.

## Supabase verification

- Project status: `ACTIVE_HEALTHY`.
- Postgres: version 17.11.
- Latest live migrations include Step 8 security hardening and Step 9 financial/storage hardening.
- All audited public business tables returned `rls_enabled=true`.
- Private buckets verified previously: `tryon-private`, `product-media`, and `product-3d`.
- Current catalog and audited test/customer counts remain zero; no test rows were added.
- Security Advisor remains at the documented intentional findings: internal-only
  `notification_events` has no client policy, and protected transaction RPCs are intentionally
  executable by authenticated users with internal authorization checks.

## Security and testing

- No provider secrets were printed, committed, or written to reports.
- Python compilation passed for `app` and `tests`.
- System Python has FastAPI/Uvicorn, but not pytest, `google-genai`, or the Supabase Python SDK.
- Full pytest remains blocked before collection; no pytest pass count is claimed.
- Existing Step 9 compatibility-runner result remains 36/36 contract functions passed, but that is
  not a pytest result.

## Missing credentials and blockers

- `GEMINI_API_KEY` and installed `google-genai`
- `TRYON_PROVIDER_URL`, `TRYON_PROVIDER_API_KEY`, and server-only `SUPABASE_SERVICE_ROLE_KEY`
- JazzCash merchant ID, password, shared secret, return URL, and authorized sandbox access
- Easypaisa merchant/store credentials, callback secret, API URL, and official assigned contract
- Isolated Supabase customer, seller, and admin test accounts
- Trusted package installation path for the pinned pytest and provider SDK dependencies
- Authorized deployment repository/hosting workspace from Step 10

The backend is not fully live or production-certified until these externally controlled blockers
are resolved and real provider responses plus authenticated non-destructive tests are completed.
