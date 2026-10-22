# Zarma Store

Production-oriented AI multi-vendor commerce platform.

## Workspace

- `backend/` — FastAPI service and secure business APIs
- `frontend/` — Next.js storefront and customer UI
- `supabase/` — database migrations and RLS
- `ai-services/` — provider adapters for search, assistant, and virtual try-on
- `n8n-workflows/` — notification and automation workflows

## Current phase

The Desktop workspace is scaffolded and the existing Zarma storefront has been reused in `frontend/`. The backend foundation exposes a health/config API. Real payments, Gemini, and virtual try-on remain disabled until provider credentials are configured; no fake success states are used.
