# Zarma Store Step 3 — Pytest Verification Report

Date: 2026-10-19 (Asia/Karachi)

## Scope

Backend-only testing and Supabase security verification. No frontend or n8n files were modified,
and no real customer data or payment was created, changed, or deleted.

## Overall status

**STEP 3: BLOCKED before pytest collection.** The existing virtual environment does not contain
pytest or the application dependencies, and the local execution environment cannot reach the
official PyPI package hosts. No pytest result is reported as passed without execution.

## Test execution evidence

| Item | Status | Result |
|---|---|---|
| Python | PASS | 3.14.5 |
| Virtual environment | PASS | `backend/.venv` exists |
| Pytest | BLOCKED | `No module named pytest` |
| FastAPI/httpx/pydantic-settings | BLOCKED | Not installed |
| Test functions present | VERIFIED | 17 source test functions in 5 test files |
| Test functions executed | 0 | Pytest failed before collection |
| Passed/failed/skipped | NOT AVAILABLE | No pytest session was created |
| Python compilation | PASS | `py -m compileall -q app tests` |
| Commission stdlib contract check | PASS | Exact 12% cases and negative input check |

The attempted command was the venv equivalent of `python -m pytest -v` and ended with:

```text
No module named pytest
```

## Test files

- `tests/test_api_smoke.py` — health, docs, OpenAPI, missing JWT, invalid request, missing provider
  configuration
- `tests/test_health.py` — health endpoint
- `tests/test_commission.py` — exact 12% commission and negative input
- `tests/test_provider_contracts.py` — catalog-only AI fallback, callback HMAC contract, rate limit
- `tests/test_ai_search_contracts.py` — intent parsing, budget/availability filtering, catalog-only
  outfit recommendations, fallback facts, and mocked Gemini SDK contract

The smoke test file compiles successfully. Its runtime tests are BLOCKED until FastAPI, httpx,
pydantic-settings, and pytest are installed.

## Feature status

| Area | Status | Evidence |
|---|---|---|
| Authentication/JWT | BLOCKED | Protected-route code and tests exist; no runtime TestClient execution |
| Customer authorization | BLOCKED | Runtime cross-user test requires isolated auth users |
| Seller applications | NOT TESTED | No isolated test users; database data untouched |
| Seller ownership/isolation | NOT TESTED | RLS source reviewed; runtime isolation test blocked |
| Admin authorization | NOT TESTED | Role tests require runtime/authenticated fixtures |
| Products/variants | NOT TESTED | Runtime tests blocked |
| Inventory/negative stock | NOT TESTED | Database RPC is present; concurrent test not executed |
| Cart/checkout/orders | NOT TESTED | Runtime tests blocked; no real order created |
| Cancellation/refunds | NOT TESTED | Runtime tests blocked; no real order changed |
| 12% commission | PASS — offline contract | 10,000→1,200/8,800; 5,000→600/4,400; 1,000→120/880; rounding and negative checks passed with stdlib |
| Wallet/withdrawals | NOT TESTED | Live financial data was not touched |
| Gemini assistant | BLOCKED | Fallback test exists; runtime dependencies and API credentials unavailable |
| Virtual try-on | BLOCKED | Provider credentials absent; no image uploaded |
| JazzCash/Easypaisa | BLOCKED | Contract code exists; merchant credentials absent; no callback applied |
| Live chat/notifications | NOT TESTED | Runtime/auth tests blocked |
| Supabase RLS | LIVE SCHEMA VERIFIED | 39 public tables with RLS, 0 public tables without RLS, 72 policies |
| Storage isolation | LIVE CONFIG VERIFIED | 3 required private buckets present |

## Supabase security verification

Read-only authorized checks against project `orhpssosozwtwynlixgj` found:

- 12 migrations applied through `withdrawal_idempotency`.
- All 39 exposed public tables have RLS enabled.
- No public table without RLS was found.
- 72 public RLS policies exist.
- `tryon-private`, `product-media`, and `product-3d` are private buckets.
- `anon` cannot execute protected financial/order RPCs.
- `authenticated` can execute `adjust_inventory`, `create_order`, and `cancel_order` as intended;
  the latter two are SECURITY DEFINER transaction entry points with auth checks.
- The idempotent four-argument seller withdrawal function is authenticated-only; the older
  three-argument overload is not executable by authenticated users.

Supabase advisors currently report one intentional internal-table INFO, two SECURITY DEFINER
warnings for authenticated transaction entry points, and performance findings including 29
unindexed foreign keys, 13 unused indexes, and 42 multiple permissive policy groups. No unsafe
policy removal or destructive database change was made.

## External providers

- Gemini: no API key configured; live integration not run.
- Try-on: no provider URL/key configured; live image generation not run.
- JazzCash/Easypaisa: no merchant IDs/callback secrets configured; no live payment or refund run.
- No fake provider success was recorded.

## Fixes and additions

- Added `tests/test_api_smoke.py`.
- Added this report.
- No backend implementation bug was safely reproducible because pytest and FastAPI could not be
  imported.
- No dependency pins, security controls, Supabase data, frontend files, or n8n files were changed.

## Remaining blockers

1. Enable an approved Codex network-enabled execution profile or use an authorized environment
   that can reach `pypi.org` and `files.pythonhosted.org`.
2. Install the pinned requirements into `backend/.venv`.
3. Run the full pytest suite and live FastAPI smoke tests.
4. Provide isolated Supabase auth test credentials if authenticated/RLS integration tests are
   authorized.
5. Provide real Gemini, try-on, JazzCash, and Easypaisa credentials for separate live-provider
   verification.
