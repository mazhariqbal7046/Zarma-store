# TryTheClothes Provider Integration Report

Date: 2026-10-20
Scope: existing Zarma Store backend only. Frontend and n8n were not modified.

## Final result

**BLOCKED — the supplied URL is a referral/invite link, not a developer API URL.**

No fake API integration was added and no customer photo was sent to TryTheClothes.

## URL inspection

Supplied URL: `https://trytheclothes.com/r/MAXHAH2XL`

The URL returned an HTML invite landing page with these observable behaviors:

- invite heading and invite-code display
- code normalization from the `/r/{code}` path
- Android deep link using `stylora://r/{code}`
- Google Play URL containing `referrer={code}`
- iOS App Store fallback with manual code entry
- no API key, bearer token, merchant endpoint, webhook endpoint, or developer configuration

The code `MAXHAH2XL` is therefore an invitation/referral code. It cannot authenticate Zarma Store
backend requests and must not be placed in `TRYON_PROVIDER_API_KEY`.

## Official site and API documentation review

The public TryTheClothes home page and FAQ describe a consumer browser/app product: upload a person
photo and clothing image, consume try-on credits, and save creations. No public developer API,
merchant API key flow, OpenAPI specification, webhook contract, or commercial backend integration
documentation was found on the official domain.

Representative developer paths checked on the official domain (`/api`, `/api/docs`, `/docs`, and
`/developer`) returned 404. The public site contains normal web application routes and client-side
internal requests, but those are not a supported third-party API contract and were not reused.

Official pages reviewed:

- [TryTheClothes referral URL](https://trytheclothes.com/r/MAXHAH2XL)
- [TryTheClothes home page](https://trytheclothes.com/)
- [TryTheClothes FAQ](https://trytheclothes.com/faq)
- [TryTheClothes privacy policy](https://trytheclothes.com/privacy)

Search results for other products such as TryOn Virtual, TryOnCloud, and TryItOn were deliberately
not used. Similar names and similar features do not establish that they are the provider behind the
submitted referral link.

## Existing Zarma backend status

The existing backend already contains a provider-neutral virtual try-on contract:

- private source uploads in Supabase Storage bucket `tryon-private`
- image MIME, magic-byte, size, and dimension validation
- authenticated customer ownership checks
- product selection against active catalog data
- asynchronous `pending`/`processing`/`completed`/`failed` job lifecycle
- worker entry points in `app.tryon_worker`
- provider submission, polling, result validation, and same-host HTTPS result protection
- private generated-result storage and short-lived signed URLs
- customer deletion/cancellation and expiry metadata

Existing endpoints include:

- `POST /api/v1/tryon/upload`
- `POST /api/v1/tryon/jobs`
- `GET /api/v1/tryon/jobs/{job_id}`
- `GET /api/v1/tryon/jobs/{job_id}/result`
- `DELETE /api/v1/tryon/jobs/{job_id}`
- `DELETE /api/v1/tryon/uploads/{upload_id}`

The generic adapter intentionally requires a documented provider contract with an HTTPS URL and
server-side API key. TryTheClothes has not supplied that contract, so it remains unconfigured.

## Verification performed

- Backend compilation: **PASSED** (`python -m compileall -q backend\\app backend\\tests`).
- Current local FastAPI server `/health`: **HTTP 200**.
- Unauthenticated `POST /api/v1/tryon/jobs`: **HTTP 401**, as required.
- No live provider generation was attempted because no provider API credentials or documented API
  endpoint exists.
- No image was uploaded to the third-party site and no mock result was created.

## Exact blocker

To perform a legitimate integration, TryTheClothes would need to provide an official commercial/API
package containing all of the following:

1. API base URL and supported virtual try-on endpoint
2. Merchant/developer API key or OAuth credential flow
3. Person-image and garment-image request format and limits
4. Synchronous or asynchronous response schema
5. Job polling/webhook signature contract, if asynchronous
6. Result-image URL/bytes and retention rules
7. Commercial usage, credit/billing, privacy, and consent terms
8. Support for server-side marketplace use, not only consumer referral credits

The referral code alone provides none of these capabilities.

## Required future configuration

Do not configure these values with the referral code:

```text
TRYON_PROVIDER_URL=<official provider API endpoint>
TRYON_PROVIDER_API_KEY=<server-only provider secret>
SUPABASE_SERVICE_ROLE_KEY=<server-only worker credential>
```

Once an official API contract and authorized credentials are supplied, the adapter should be
implemented specifically for that contract and verified with one consented test image, one active
product image, private Supabase storage, signed result access, deletion, and provider failure tests.

## Classification

- Referral URL classification: **LIVE VERIFIED**
- Official TryTheClothes developer API: **BLOCKED / NOT FOUND**
- Existing Zarma try-on storage and authorization: **LIVE SCHEMA VERIFIED / LOCAL TEST PASSED**
- TryTheClothes generation: **BLOCKED**
- Third-party credentials: **MISSING**
- Fake/mock integration: **NOT IMPLEMENTED**
