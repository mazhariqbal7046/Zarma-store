# Step 6 — JazzCash, Easypaisa, Digital Wallet and Financial Safety

Date: 2026-10-19  
Scope: backend and Supabase only. Frontend and n8n were not modified.

## Overall status

Core financial database safety is **LIVE VERIFIED**. JazzCash request/hash code is **LOCAL TEST PASSED** but live/sandbox execution is **BLOCKED BY CREDENTIALS**. Easypaisa is **IMPLEMENTED BUT UNVERIFIED / BLOCKED BY MERCHANT CONTRACT**. No real payment, refund, payout, or customer data mutation was executed.

## JazzCash

- Added a JazzCash-specific hosted checkout form adapter with PKR amount, unique transaction reference, expiry, return URL, merchant fields, and `pp_SecureHash`.
- Implemented the official PP-field HMAC-SHA256 ordering and verified the published vector locally.
- Callback handling derives status from signed provider fields, validates amount through an atomic Supabase RPC, records an event once, and rejects replayed events.
- Live sandbox test: **BLOCKED** because merchant ID, password, shared secret, and authorized sandbox account are absent.

Official reference: [JazzCash sandbox API references](https://sandbox.jazzcash.com.pk/SandboxDocumentation/v4.2/ApiReferences.html) and [JazzCash integration guide](https://payments.jazzcash.com.pk/SandboxDocumentation/Content/documentation/Payment%20Gateway%20Integration%20Guide%20for%20Merchants-v4.2.pdf).

## Easypaisa

- Added a separate Easypaisa callback/adapter contract; JazzCash hashing is not reused.
- Live mode remains disabled unless `EASYPAISA_CONTRACT_VERIFIED=true` is explicitly configured after the merchant-specific official contract is obtained and reviewed.
- Live/sandbox test: **BLOCKED**; the official integration guide is merchant-portal gated and no merchant credentials were available.

Official reference: [Easypaisa merchant integration guides](https://easypay.easypaisa.com.pk/easypay-merchant/faces/pg/site/IntegrationGuides.jsf).

## Database and wallet

Migrations applied remotely as `20261019182808_payments_wallet_safety_step6` and
`20261019183108_payment_event_index_cleanup`.

- Added `payment_attempts` with idempotency and provider-reference uniqueness.
- Added `refunds` with idempotency, provider reference, status, and requested-by fields.
- Preserved the original unique `(provider, provider_event_id)` payment replay protection and
  removed a redundant duplicate index after Supabase Advisor identified it.
- Added atomic RPCs: `begin_payment_attempt`, `process_payment_event`, `create_refund_request`, and `admin_set_withdrawal_status`.
- Payment callbacks verify provider, event uniqueness, order ownership mapping, PKR amount, and valid state transitions before marking paid/refunded.
- Refund confirmation credits the customer’s internal wallet exactly once through the wallet ledger and locked balance update.
- Wallet exposes available balance, pending balance, and transaction history. The wallet is internal ledger credit, not licensed stored value or a bank account.
- Sensitive provider secrets are server-only; no secrets were committed.

## 12% commission

The existing database commission trigger was preserved. It uses NUMERIC/ bigint-safe arithmetic, unique order/seller records, and exactly `0.1200`. Existing local tests cover:

- PKR 10,000 → PKR 1,200 commission / PKR 8,800 seller net.
- PKR 5,000 → PKR 600 commission / PKR 4,400 seller net.
- PKR 1,000 → PKR 120 commission / PKR 880 seller net.

No live order rows existed for a destructive or customer-affecting financial test.

## Seller withdrawals

- Existing idempotency-key request RPC preserved and upgraded to subtract `withdrawn_pkr` from earnings.
- Paid withdrawals now allocate earnings under row locks, preventing already-paid earnings from becoming withdrawable again.
- Added admin approval, rejection, paid, and failed status endpoint.
- A paid withdrawal requires an admin role and payout reference; no external payout was performed.
- Concurrent/insufficient balance protection remains database-locked and idempotent.

## API endpoints

- `POST /api/v1/payments/initiate`
- `GET /api/v1/payments/{payment_id}`
- `POST /api/v1/payments/jazzcash/callback`
- `POST /api/v1/payments/easypaisa/callback`
- `POST /api/v1/payments/{payment_id}/refund` — admin-only pending refund request
- `GET /api/v1/wallet`
- `GET /api/v1/wallet/transactions`
- `POST /api/v1/seller/withdrawals`
- `GET /api/v1/seller/earnings`
- `PATCH /api/v1/admin/withdrawals/{withdrawal_id}`

## Verification

- `py -m compileall -q app tests`: **PASSED**.
- System-Python local contract checks: **PASSED**.
- JazzCash official hash vector: **PASSED**.
- Real Uvicorn HTTP smoke: `/health` 200, `/docs` 200, `/openapi.json` 200.
- Supabase migration, tables, columns, functions, and RLS: **LIVE VERIFIED**.
- Supabase security advisor: only intentional warnings for authenticated execution of protected
  transaction entry points; `notification_events` remains intentionally internal-only.
- Supabase performance advisor: existing unindexed foreign-key and multiple-permissive-policy
  findings remain; the Step 6 duplicate payment-event index warning was removed.
- Full pytest: **BLOCKED** — `pytest` is not installed in the available `.venv`, and PyPI access is unavailable in this environment.
- Authorized sandbox payments/refunds/payouts: **NOT RUN** — no credentials or financial authorization.

## Missing credentials / blockers

```text
SUPABASE_SERVICE_ROLE_KEY
JAZZCASH_MERCHANT_ID
JAZZCASH_PASSWORD
JAZZCASH_SHARED_SECRET
JAZZCASH_RETURN_URL
EASYPAISA_MERCHANT_ID
EASYPAISA_STORE_ID
EASYPAISA_API_URL
EASYPAISA_CALLBACK_SECRET
EASYPAISA_CONTRACT_VERIFIED=true  # only after official contract review
```

The backend is not marked fully live because real provider verification, payment certification, refunds, and payouts require merchant onboarding and authorized credentials.
