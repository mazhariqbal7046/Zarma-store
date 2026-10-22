# Step 5 — AI Virtual Try-On Mirror Backend

Date: 2026-10-19  
Scope: backend only. Frontend and n8n were not modified.

## Result

The backend implementation is complete as an integration contract, but live AI generation is **blocked** until a real virtual try-on provider URL and API key are supplied. No mock image is returned and no generated result is claimed when the provider is unavailable.

## Implemented

- Private source-image uploads in Supabase Storage bucket `tryon-private`.
- Additive `tryon_uploads` table with RLS, user ownership, MIME/size constraints, SHA-256 deduplication, expiry metadata, and soft deletion.
- JPEG, PNG, and WebP MIME plus magic-byte validation; dimensions are limited to 64–4096 pixels and files to 10 MiB.
- UUID-based storage paths; original filenames are not used in paths.
- Product selection against active catalog products.
- Durable database-backed job lifecycle: `pending` → `processing` → `completed` or `failed`; user cancellation uses `cancelled`. Legacy `queued`/`deleted` enum values remain for compatibility.
- Generic HTTPS provider adapter with authenticated submission, polling, result validation, and provider-host SSRF protection.
- Worker entry points: `app.tryon_worker.run_once`, `process_tryon_job`, and `python -m app.tryon_worker`.
- Signed result URLs remain private and expire after 300 seconds.
- Customer-owned job and upload authorization is enforced through API filters and Supabase RLS.
- Custom clothing measurements remain a separate sizing feature; they are not presented as visual fit accuracy.

## API endpoints

- `POST /api/v1/tryon/upload` — authenticated private source upload.
- `POST /api/v1/tryon/jobs` — authenticated job creation from an upload and active product.
- `GET /api/v1/tryon/jobs/{job_id}` — own job status.
- `GET /api/v1/tryon/jobs/{job_id}/result` — own completed result as a short-lived signed URL.
- `DELETE /api/v1/tryon/jobs/{job_id}` — cancel and delete own source/result objects.
- `DELETE /api/v1/tryon/uploads/{upload_id}` — delete an unused own source upload.
- Existing compatibility routes remain: `/api/v1/ai/try-on` and `/api/v1/ai/try-on/{job_id}` plus result/delete routes.

## Supabase verification

- Target project: `orhpssosozwtwynlixgj`.
- Migration applied successfully through the Supabase integration as `tryon_uploads_and_lifecycle` (remote migration version `20261019182207`).
- `public.tryon_uploads` exists, has RLS enabled, and has one authenticated-user ownership policy.
- `public.ai_tryon_jobs` now supports `pending` and `cancelled` in addition to existing values.
- `tryon-private`, `product-media`, and `product-3d` are private buckets.
- The live catalog currently has zero product rows, so no live product/job generation was attempted.
- No existing rows were deleted or rewritten.

## Verification evidence

- `py -m compileall -q app tests`: passed.
- Backend import and OpenAPI contract: passed; 54 paths loaded, including all new try-on paths.
- Real local HTTP smoke test with Uvicorn: `/health` 200, `/docs` 200, `/openapi.json` 200.
- `pytest`: blocked because `pytest` is not installed in the available Python 3.14 environment and package installation cannot reach PyPI from this execution environment.
- Live provider submission, storage upload, signed URL, and authenticated RLS tests: not run because there are no test credentials/users, no live catalog rows, and no provider credentials.

## Missing credentials / blockers

Required for live generation:

```text
TRYON_PROVIDER_URL=https://<approved-provider-endpoint>
TRYON_PROVIDER_API_KEY=<provider-secret>
SUPABASE_SERVICE_ROLE_KEY=<server-only-secret-for-worker>
```

The configured provider must document the adapter contract used in `app/tryon_provider.py` or receive a provider-specific adapter implementation. The API key and service-role key must stay server-side and must never be committed or exposed to the frontend.

The current environment also cannot install the pinned Python dependencies because HTTPS access to PyPI/file hosts times out. This blocks pytest and a full FastAPI dependency-based test run; it is an environment limitation, not a reported test pass.
