import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.settings import settings


_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def _http_client() -> httpx.AsyncClient:
    """Reuse a connection pool so each API request does not repeat TLS setup."""

    global _client
    if _client is None or _client.is_closed:
        async with _client_lock:
            if _client is None or _client.is_closed:
                _client = httpx.AsyncClient(
                    base_url=f"{settings.supabase_url.rstrip('/')}/rest/v1",
                    timeout=15,
                )
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    role: str
    access_token: str
    email: str | None = None


class SupabaseRestError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.raw_detail = str(detail)
        if status_code in (401, 403):
            self.detail = "Authentication or authorization failed"
        elif status_code == 404:
            self.detail = "Requested resource was not found"
        elif status_code == 409:
            self.detail = "Request conflicts with the current state"
        elif status_code == 422:
            self.detail = "Request validation failed"
        elif status_code >= 500:
            self.detail = "Upstream service is unavailable"
        else:
            self.detail = "Request could not be completed"


def _headers(access_token: str | None = None) -> dict[str, str]:
    headers = {"apikey": settings.supabase_publishable_key, "Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _service_headers() -> dict[str, str]:
    server_key = settings.supabase_service_role_key or settings.supabase_secret_key
    if not server_key:
        raise SupabaseRestError(503, "A server-only Supabase service or secret key is required for protected admin operations")
    return {"apikey": server_key, "Authorization": f"Bearer {server_key}", "Content-Type": "application/json"}


async def rest_request(method: str, table: str, access_token: str, *, params: dict[str, str] | None = None, body: Any = None, prefer: str | None = None) -> Any:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise SupabaseRestError(503, "Supabase credentials are not configured")
    headers = _headers(access_token)
    if prefer:
        headers["Prefer"] = prefer
    client = await _http_client()
    response = await client.request(method, f"/{table}", headers=headers, params=params, json=body)
    if response.is_error:
        raise SupabaseRestError(response.status_code, response.text)
    if not response.content:
        return None
    return response.json()


async def rpc_request(function_name: str, access_token: str, body: dict[str, Any]) -> Any:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise SupabaseRestError(503, "Supabase credentials are not configured")
    client = await _http_client()
    response = await client.post(f"/rpc/{function_name}", headers=_headers(access_token), json=body)
    if response.is_error:
        raise SupabaseRestError(response.status_code, response.text)
    return response.json() if response.content else None


async def privileged_rpc_request(function_name: str, body: dict[str, Any]) -> Any:
    if not settings.supabase_url:
        raise SupabaseRestError(503, "Supabase credentials are not configured")
    async with httpx.AsyncClient(base_url=f"{settings.supabase_url}/rest/v1", timeout=15) as client:
        response = await client.post(f"/rpc/{function_name}", headers=_service_headers(), json=body)
    if response.is_error:
        raise SupabaseRestError(response.status_code, response.text)
    return response.json() if response.content else None


async def storage_upload(bucket: str, path: str, access_token: str, content: bytes, content_type: str) -> None:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise SupabaseRestError(503, "Supabase credentials are not configured")
    headers = _headers(access_token)
    headers["Content-Type"] = content_type
    headers["x-upsert"] = "false"
    object_path = quote(path, safe="/")
    client = await _http_client()
    response = await client.post(f"{settings.supabase_url}/storage/v1/object/{bucket}/{object_path}", headers=headers, content=content, timeout=30)
    if response.is_error:
        raise SupabaseRestError(response.status_code, response.text)


async def storage_download(bucket: str, path: str, access_token: str) -> tuple[bytes, str]:
    if not settings.supabase_url:
        raise SupabaseRestError(503, "Supabase credentials are not configured")
    headers = _headers(access_token)
    headers.pop("Content-Type", None)
    object_path = quote(path, safe="/")
    client = await _http_client()
    response = await client.get(f"{settings.supabase_url}/storage/v1/object/{bucket}/{object_path}", headers=headers, timeout=30)
    if response.is_error:
        raise SupabaseRestError(response.status_code, response.text)
    return response.content, response.headers.get("content-type", "application/octet-stream").split(";", 1)[0]


async def storage_signed_url(bucket: str, path: str, access_token: str, expires_in: int = 300) -> str:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise SupabaseRestError(503, "Supabase credentials are not configured")
    object_path = quote(path, safe="/")
    client = await _http_client()
    response = await client.post(f"{settings.supabase_url}/storage/v1/object/sign/{bucket}/{object_path}", headers=_headers(access_token), json={"expiresIn": expires_in})
    if response.is_error:
        raise SupabaseRestError(response.status_code, response.text)
    data = response.json()
    return data.get("signedURL") or data.get("signedUrl") or ""


async def storage_delete(bucket: str, path: str, access_token: str) -> None:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise SupabaseRestError(503, "Supabase credentials are not configured")
    object_path = quote(path, safe="/")
    client = await _http_client()
    response = await client.request("DELETE", f"{settings.supabase_url}/storage/v1/object/{bucket}/{object_path}", headers=_headers(access_token))
    if response.is_error:
        raise SupabaseRestError(response.status_code, response.text)


async def privileged_request(method: str, table: str, *, params: dict[str, str] | None = None, body: Any = None, prefer: str | None = None) -> Any:
    if not settings.supabase_url:
        raise SupabaseRestError(503, "Supabase credentials are not configured")
    headers = _service_headers()
    if prefer:
        headers["Prefer"] = prefer
    client = await _http_client()
    response = await client.request(method, f"/{table}", headers=headers, params=params, json=body)
    if response.is_error:
        raise SupabaseRestError(response.status_code, response.text)
    return response.json() if response.content else None


async def authenticate(access_token: str) -> AuthContext:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise SupabaseRestError(503, "Supabase credentials are not configured")
    client = await _http_client()
    response = await client.get(f"{settings.supabase_url}/auth/v1/user", headers=_headers(access_token))
    if response.is_error:
        raise SupabaseRestError(401, "Invalid or expired session")
    auth_user = response.json()
    user_id = auth_user.get("id")
    email = auth_user.get("email")
    profile = await rest_request("GET", "profiles", access_token, params={"id": f"eq.{user_id}", "select": "role,account_status", "limit": "1"})
    profile_data = profile[0] if profile else {}
    if profile_data.get("account_status", "active") != "active":
        raise SupabaseRestError(403, "Account is not active")
    role = profile_data.get("role", "customer")
    if role != "admin":
        seller = await rest_request("GET", "sellers", access_token, params={"user_id": f"eq.{user_id}", "active": "eq.true", "select": "id", "limit": "1"})
        if seller:
            role = "seller"
    return AuthContext(user_id=user_id, role=role, access_token=access_token, email=email)
