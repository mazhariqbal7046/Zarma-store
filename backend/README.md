# Zarma Store Backend

FastAPI service for authenticated commerce operations, seller APIs, AI orchestration, and verified payment callbacks.

## Run

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

The backend never treats a browser payment response as proof of success. Payment adapters and callbacks must verify the provider signature before updating the ledger.

## Implemented API areas

- Bearer JWT verification through Supabase Auth
- Customer seller applications and admin approval/rejection
- Seller-owned product CRUD, variants, private media uploads, and atomic inventory adjustment RPC
- Public catalog search, authenticated cart, order history, and atomic checkout RPC
- Database commission ledger trigger at exactly 12% of eligible order-item selling price
- Grounded AI search/assistant with deterministic catalog fallback and persisted conversations
- Private try-on upload, job status, signed result URL, and deletion contract
- Wallet/earnings reads, locked seller withdrawal request RPC, and admin analytics
- Wishlist, reviews, support conversations/messages, notifications, coupons/discounts, 3D asset metadata
- Payment initiation/status and signature-verified callback contract for JazzCash/Easypaisa
- Admin customer, order, transaction, and withdrawal reporting endpoints
- Seller withdrawal request endpoint

The Supabase SQL migrations are in the repository root under `../supabase/migrations`; the current
sequence has been applied to project `orhpssosozwtwynlixgj` through the Supabase MCP connection.
AI generation, JazzCash/Easypaisa live processing, and try-on job workers remain disabled until
their credentials and provider contracts are supplied. No n8n workflow is implemented here.

Admin endpoints require both a verified session whose `profiles.role` is `admin` and the server-only `SUPABASE_SERVICE_ROLE_KEY` for privileged reporting queries. Public signup never assigns that role.
