from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from app.settings import settings


class TryOnProviderUnavailable(RuntimeError):
    pass


class TryOnProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class TryOnSubmission:
    provider_job_id: str | None
    status: str
    result_url: str | None = None


class GenericTryOnProvider:
    """Adapter for a documented provider contract configured by the deployment.

    The backend deliberately does not invent a provider-specific payload. The configured
    endpoint must accept multipart fields named person_image, garment_image, category,
    and request_id, and return {job_id, status, result_url?}. This keeps live generation
    disabled until the merchant supplies a real provider and credentials.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.tryon_provider_url).rstrip("/")
        self.api_key = api_key or settings.tryon_provider_api_key
        if not self.base_url or not self.api_key:
            raise TryOnProviderUnavailable(
                "TRYON_PROVIDER_URL and TRYON_PROVIDER_API_KEY are required; live try-on is unavailable"
            )
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise TryOnProviderUnavailable("TRYON_PROVIDER_URL must be an HTTPS URL")

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    def _url(self, path: str = "") -> str:
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    def _assert_safe_result_url(self, result_url: str) -> str:
        parsed = urlparse(result_url)
        base = urlparse(self.base_url)
        if parsed.scheme != "https" or parsed.netloc != base.netloc:
            raise TryOnProviderError("Provider returned a result URL outside the configured provider host")
        return result_url

    @staticmethod
    def _submission(data: dict) -> TryOnSubmission:
        provider_job_id = data.get("job_id") or data.get("id")
        status = str(data.get("status") or "processing").lower()
        result_url = data.get("result_url") or data.get("resultUrl")
        if result_url:
            result_url = str(result_url)
        if not provider_job_id and not result_url:
            raise TryOnProviderError("Provider response did not contain a job id or result URL")
        return TryOnSubmission(str(provider_job_id) if provider_job_id else None, status, result_url)

    async def submit(
        self,
        person_image: bytes,
        person_mime: str,
        garment_image: bytes,
        garment_mime: str,
        category: str,
        request_id: str,
    ) -> TryOnSubmission:
        files = {
            "person_image": ("person", person_image, person_mime),
            "garment_image": ("garment", garment_image, garment_mime),
        }
        data = {"category": category, "request_id": request_id}
        try:
            async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
                response = await client.post(self._url("jobs"), headers=self._headers, data=data, files=files)
        except httpx.HTTPError as error:
            raise TryOnProviderError("Could not reach the configured try-on provider") from error
        if response.is_error:
            raise TryOnProviderError(f"Try-on provider rejected the request ({response.status_code})")
        try:
            return self._submission(response.json())
        except (ValueError, TypeError, KeyError) as error:
            raise TryOnProviderError("Try-on provider returned an invalid response") from error

    async def poll(self, provider_job_id: str) -> TryOnSubmission:
        try:
            async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
                response = await client.get(self._url(f"jobs/{provider_job_id}"), headers=self._headers)
        except httpx.HTTPError as error:
            raise TryOnProviderError("Could not reach the configured try-on provider") from error
        if response.is_error:
            raise TryOnProviderError(f"Try-on provider status request failed ({response.status_code})")
        try:
            return self._submission(response.json())
        except (ValueError, TypeError, KeyError) as error:
            raise TryOnProviderError("Try-on provider returned an invalid status response") from error

    async def download_result(self, result_url: str) -> tuple[bytes, str]:
        safe_url = self._assert_safe_result_url(result_url)
        try:
            async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
                response = await client.get(safe_url, headers=self._headers)
        except httpx.HTTPError as error:
            raise TryOnProviderError("Could not download the provider result") from error
        if response.is_error or not response.content:
            raise TryOnProviderError("Provider result download failed")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise TryOnProviderError("Provider returned a non-image result")
        return response.content, content_type
