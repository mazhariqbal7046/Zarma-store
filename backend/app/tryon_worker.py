from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.settings import settings
from app.supabase_rest import SupabaseRestError, privileged_request, storage_download, storage_upload
from app.tryon_images import validate_image
from app.tryon_provider import GenericTryOnProvider, TryOnProviderError, TryOnProviderUnavailable, TryOnSubmission


def _service_token() -> str:
    if not settings.supabase_service_role_key:
        raise SupabaseRestError(503, "SUPABASE_SERVICE_ROLE_KEY is required for the try-on worker")
    return settings.supabase_service_role_key


def _product_image_path(product: dict) -> str | None:
    images = product.get("product_images") or []
    if not images:
        return None
    ordered = sorted(images, key=lambda item: item.get("sort_order", 0))
    return ordered[0].get("storage_path")


async def _fail(job_id: str, message: str) -> None:
    await privileged_request(
        "PATCH",
        "ai_tryon_jobs",
        params={"id": f"eq.{job_id}", "status": "eq.processing"},
        body={"status": "failed", "error_message": message[:1000]},
    )


async def _finish(job_id: str, result_path: str) -> None:
    await privileged_request(
        "PATCH",
        "ai_tryon_jobs",
        params={"id": f"eq.{job_id}", "status": "eq.processing"},
        body={
            "status": "completed",
            "result_image_path": result_path,
            "error_message": None,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    )


async def _poll_to_result(provider: GenericTryOnProvider, submission: TryOnSubmission) -> tuple[bytes, str]:
    current = submission
    for _ in range(6):
        if current.result_url:
            return await provider.download_result(current.result_url)
        if current.status in {"failed", "error", "cancelled"}:
            raise TryOnProviderError("Try-on provider reported a failed job")
        if not current.provider_job_id:
            raise TryOnProviderError("Try-on provider did not return a pollable job id")
        await asyncio.sleep(2)
        current = await provider.poll(current.provider_job_id)
    raise TryOnProviderError("Try-on provider job did not complete within the worker polling window")


async def process_tryon_job(job_id: str) -> dict:
    """Claim and process one durable DB-backed job; safe to call from a worker process."""
    token = _service_token()
    rows = await privileged_request(
        "PATCH",
        "ai_tryon_jobs",
        params={"id": f"eq.{job_id}", "status": "in.(pending,queued)", "select": "*"},
        body={"status": "processing", "error_message": None},
        prefer="return=representation",
    )
    if not rows:
        return {"id": job_id, "status": "not_claimed"}
    job = rows[0]
    try:
        provider = GenericTryOnProvider()
        products = await privileged_request(
            "GET", "products", params={"id": f"eq.{job['product_id']}", "active": "eq.true", "select": "id,product_images(*)", "limit": "1"}
        )
        if not products:
            raise TryOnProviderError("Selected product is no longer available")
        garment_path = _product_image_path(products[0])
        if not garment_path:
            raise TryOnProviderError("Selected product has no usable image")

        source, source_mime = await storage_download("tryon-private", job["source_image_path"], token)
        garment, garment_mime = await storage_download("product-media", garment_path, token)
        validate_image(source, source_mime)
        validate_image(garment, garment_mime)
        submission = await provider.submit(source, source_mime, garment, garment_mime, "upper_body", job_id)
        if submission.provider_job_id:
            await privileged_request(
                "PATCH",
                "ai_tryon_jobs",
                params={"id": f"eq.{job_id}", "status": "eq.processing"},
                body={"provider": "configured", "provider_job_id": submission.provider_job_id},
            )
        result, result_mime = await _poll_to_result(provider, submission)
        validated = validate_image(result, result_mime)
        result_path = f"{job['user_id']}/{job_id}/result-{uuid4()}.{result_mime.split('/')[-1].replace('jpeg', 'jpg')}"
        await storage_upload("tryon-private", result_path, token, validated.content, validated.mime_type)
        await _finish(job_id, result_path)
        return {"id": job_id, "status": "completed"}
    except (TryOnProviderUnavailable, TryOnProviderError, SupabaseRestError, ValueError) as error:
        message = str(error) or "Try-on processing failed"
        try:
            await _fail(job_id, message)
        except SupabaseRestError:
            pass
        return {"id": job_id, "status": "failed", "error": message}


async def run_once(limit: int = 10) -> list[dict]:
    rows = await privileged_request(
        "GET",
        "ai_tryon_jobs",
        params={"status": "in.(pending,queued)", "order": "created_at.asc", "limit": str(max(1, min(limit, 50))), "select": "id"},
    )
    return [await process_tryon_job(row["id"]) for row in rows]


async def run_forever(poll_seconds: float = 3.0) -> None:
    while True:
        await run_once()
        await asyncio.sleep(max(1.0, poll_seconds))


if __name__ == "__main__":
    asyncio.run(run_forever())
