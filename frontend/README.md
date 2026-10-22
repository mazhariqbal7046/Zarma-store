# Zarma Meni Mart

Production-oriented foundation for a Pakistani menswear shop with a server-validated catalog, Supabase-backed commerce model, and Gemini shopping assistant seam.

## Run locally

```bash
npm install
copy .env.example .env.local
npm run dev
```

The homepage uses the FastAPI backend at `NEXT_PUBLIC_BACKEND_URL` for the catalog, AI search, authenticated AI assistant, and cart actions. If the backend catalog is empty or unavailable, the existing fixture remains visible as a clearly non-live visual preview; no preview item is sent to checkout.

## Environment

See `.env.example`. Never place `SUPABASE_SERVICE_ROLE_KEY` or `GEMINI_API_KEY` in client-side code. `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` is the only browser-safe Supabase key.

## Supabase

Apply `supabase/migrations/202610090001_initial_schema.sql` through the Supabase migration workflow. Before production, add a server-side transaction/RPC for checkout that revalidates prices, reserves stock, and uses the order `idempotency_key`. Admin authorization should be assigned in `profiles.role` or trusted app metadata, never user-editable metadata.

## Backend integration

`lib/backend-api.ts` is the single browser-safe client for the FastAPI routes. It obtains the current Supabase access token in the browser and sends it only as an Authorization header to protected backend endpoints. It contains customer, seller, admin, support, try-on, wallet, payment, catalog, and AI route wrappers. Provider callbacks remain backend-only.

Run the backend at `http://127.0.0.1:8000` and the frontend at `http://localhost:3000`. The frontend `.env.local` is local-only and must never contain service-role, Gemini, payment, or other privileged secrets.

## Status

The storefront is connected to the existing backend API. The LinkedIn reference supplied for this task is an announcement post rather than a UI template, so no external code or untrusted instructions were imported from it. Real catalog rows, Gemini credentials, payment gateway approval, and provider-specific production credentials remain environment-dependent.
