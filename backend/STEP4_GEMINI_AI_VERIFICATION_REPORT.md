# Zarma Store Step 4 — Gemini AI Verification Report

Date: 2026-10-19 (Asia/Karachi)

## Scope

Backend AI code only. Frontend and n8n files were not modified. No Gemini key, Supabase service
role key, customer data, or product data was exposed or changed.

## Overall status

**IMPLEMENTED BUT LIVE VERIFICATION BLOCKED.** The Gemini adapter now uses the official
`google-genai` SDK contract, while deterministic catalog filtering and fallback behavior work
without Gemini. The SDK cannot be installed because PyPI access is blocked in the current Codex
execution environment, and no `GEMINI_API_KEY` is configured.

## SDK and configuration

| Item | Status | Result |
|---|---|---|
| SDK dependency | CONFIGURED | `google-genai==2.31.0` added to `requirements.txt` |
| SDK installed | BLOCKED | `google.genai` unavailable in `backend/.venv` |
| Model | CONFIGURED | `gemini-flash-latest`, overridable with `GEMINI_MODEL` |
| API key | BLOCKED | `GEMINI_API_KEY` absent; no fabricated key used |
| Timeout/retry | IMPLEMENTED | bounded timeout plus one safe retry |
| Secret handling | PASS | key is read only from settings and never logged or returned |

The SDK usage follows Google's documented `genai.Client(api_key=...).aio.models.generate_content`
pattern. The current SDK metadata lists Python 3.14 support and recommends pinning below the next
major version; the exact dependency is pinned here.

## Implemented features

- Deterministic natural-language intent parsing for colors, Roman Urdu aliases, categories, sizes,
  budgets, seller terms, and availability.
- Server-side filtering and ranking of only Supabase catalog records.
- Budget filtering such as `under 3000` and `3k`.
- Variant color/size checks and optional inventory availability checks.
- Real-catalog outfit recommendations across shirts, trousers, shoes, jackets, accessories, and
  dresses; no generated product IDs or names.
- Optional Gemini structured JSON intent extraction with strict allowlisted fields and deterministic
  fallback.
- Gemini assistant prompt hardening against prompt injection and unauthorized data changes.
- Conversation history loading restricted by authenticated `user_id`.
- Conversation list, read, and delete APIs with ownership filters.
- `/api/v1/ai/chat` alias while preserving `/api/v1/ai/assistant`.
- `/api/v1/ai/search` and `/api/v1/ai/outfit` real-catalog endpoints.
- Existing `/api/v1/ai/assistant` preserved and enhanced with recommendations/history.
- AI rate limiting remains enabled.

## API routes

- `POST /api/v1/ai/search`
- `POST /api/v1/ai/chat`
- `POST /api/v1/ai/assistant`
- `POST /api/v1/ai/outfit`
- `GET /api/v1/ai/conversations`
- `GET /api/v1/ai/conversations/{conversation_id}`
- `DELETE /api/v1/ai/conversations/{conversation_id}`

The backend now has 55 API-router routes plus 2 system routes by static inspection. FastAPI OpenAPI
runtime output is not available until dependencies are installed.

## Verification results

| Check | Status | Evidence |
|---|---|---|
| Python compilation | PASS | `py -m compileall -q app tests` |
| Catalog intent/filter contract | PASS | Isolated standard-library execution |
| Outfit recommendation contract | PASS | Returned only supplied catalog records |
| Fallback response contract | PASS | Returned supplied product name/price only |
| Mocked Gemini SDK contract | PASS | Verified client, model, JSON config, and parsed intent |
| Pytest suite | BLOCKED | `No module named pytest` |
| FastAPI HTTP tests | BLOCKED | FastAPI/Uvicorn unavailable |
| Live Gemini request | BLOCKED | SDK unavailable and API key absent |
| Live AI search | BLOCKED | FastAPI runtime unavailable; Supabase catalog currently has 0 rows |
| Live conversation memory | BLOCKED | Authenticated HTTP test unavailable |

The mocked SDK check is not a live Gemini success claim. The offline catalog checks use controlled
fixtures and do not represent live product availability.

## Supabase integration

- AI routes query active products from Supabase and include categories, images, variants, and nested
  inventory fields where RLS permits access.
- Explicit in-stock searches use the server-only service key for the inventory aggregate only when
  it is configured; without it, unknown inventory is excluded rather than presented as available.
- AI logs remain user-scoped through `ai_search_logs`.
- Conversation reads/writes/deletes include the authenticated user's ownership filter.
- Supabase project connectivity and RLS were previously live-verified; no AI database migration
  was necessary.
- Remote public catalog row count currently reports zero, so no live product recommendation could be
  honestly demonstrated.

## Security status

- Gemini receives catalog/order/history data only; it has no database or mutation tools.
- JSON intent output is restricted to allowlisted fields and validated server-side.
- Prompt injection text is treated as untrusted data.
- Protected assistant/conversation routes require JWT authentication.
- Anonymous search/outfit routes use only public catalog data.
- Runtime JWT, cross-user conversation, and RLS tests remain BLOCKED by missing dependencies and
  isolated auth credentials.

## Remaining blockers

1. Approved network access to install pinned dependencies, including `google-genai==2.31.0`.
2. Secure `GEMINI_API_KEY` in the local deployment environment.
3. At least one active Supabase product/variant fixture for live catalog verification.
4. Isolated authenticated test users for conversation ownership and AI log tests.
5. FastAPI startup and full pytest execution after dependency installation.
