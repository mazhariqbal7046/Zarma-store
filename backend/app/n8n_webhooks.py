"""Signed, retrying n8n Cloud delivery for server-created order events."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

from app.settings import settings
from app.supabase_rest import SupabaseRestError, rpc_request

logger = logging.getLogger("zarma.n8n")
_local_delivered: OrderedDict[str, float] = OrderedDict()
_local_lock = asyncio.Lock()
_MAX_LOCAL_EVENTS = 10_000


def _event_id(order_id: str) -> str:
    return f"order.created:{order_id}"


def sign_payload(payload: bytes, secret: str) -> str:
    """Return the header value n8n should verify: sha256=<hex digest>."""
    return "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _safe_order_payload(order: dict[str, Any], user_id: str, items: list[dict[str, Any]] | None) -> dict[str, Any]:
    allowed = ("id", "status", "subtotal_pkr", "delivery_pkr", "discount_pkr", "total_pkr", "created_at")
    data = {key: order.get(key) for key in allowed if key in order}
    data.update({"order_id": str(order.get("id") or order.get("order_id")), "user_id": user_id})
    if items:
        data["items"] = [
            {key: item.get(key) for key in ("variant_id", "quantity") if key in item}
            for item in items
        ]
    return data


async def _send_once(payload: bytes, event_id: str) -> httpx.Response:
    headers = {
        "Content-Type": "application/json",
        "X-Zarma-Event": "order.created",
        "X-Zarma-Event-Id": event_id,
        "X-Zarma-Signature": sign_payload(payload, settings.n8n_webhook_secret),
        "X-Zarma-Webhook-Secret": settings.n8n_webhook_secret,
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        return await client.post(settings.n8n_order_webhook_url, content=payload, headers=headers)


async def deliver_new_order(
    order: dict[str, Any],
    user_id: str,
    items: list[dict[str, Any]] | None = None,
    access_token: str | None = None,
) -> bool:
    """Deliver once per order. Returns True only when n8n accepted the event."""
    if not settings.n8n_order_webhook_url or not settings.n8n_webhook_secret:
        return False
    order_id = str(order.get("id") or order.get("order_id") or "")
    if not order_id:
        logger.warning("n8n_order_missing_id")
        return False
    try:
        UUID(order_id)
    except ValueError:
        logger.warning("n8n_order_invalid_id")
        return False

    event_id = _event_id(order_id)
    persistent_claim = False
    if access_token:
        try:
            claimed = await rpc_request("claim_n8n_order_notification", access_token, {"p_order_id": order_id})
            if claimed is False:
                return True
            persistent_claim = True
        except SupabaseRestError as error:
            # The migration may not yet be applied in a local environment. Keep the
            # integration usable with the bounded process-local guard until then.
            if error.status_code != 404:
                logger.warning("n8n_persistent_claim_unavailable status=%s", error.status_code)
    async with _local_lock:
        if not persistent_claim and event_id in _local_delivered:
            return True
    envelope = {
        "event_id": event_id,
        "event_type": "order.created",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": _safe_order_payload(order, user_id, items),
    }
    payload = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")
    for attempt in range(3):
        try:
            response = await _send_once(payload, event_id)
            if 200 <= response.status_code < 300:
                if persistent_claim and access_token:
                    try:
                        await rpc_request("complete_n8n_order_notification", access_token, {"p_order_id": order_id})
                    except SupabaseRestError:
                        logger.warning("n8n_persistent_completion_unavailable")
                async with _local_lock:
                    _local_delivered[event_id] = datetime.now(timezone.utc).timestamp()
                    _local_delivered.move_to_end(event_id)
                    while len(_local_delivered) > _MAX_LOCAL_EVENTS:
                        _local_delivered.popitem(last=False)
                return True
            if 400 <= response.status_code < 500:
                logger.error("n8n_order_rejected status=%s", response.status_code)
                return False
            logger.warning("n8n_order_retry status=%s attempt=%s", response.status_code, attempt + 1)
        except (httpx.HTTPError, TimeoutError) as error:
            logger.warning("n8n_order_retry error=%s attempt=%s", type(error).__name__, attempt + 1)
        if attempt < 2:
            await asyncio.sleep(0.25 * (2**attempt))
    logger.error("n8n_order_delivery_failed")
    return False


async def deliver_customer_registered(user_id: str, email: str | None, full_name: str | None) -> bool:
    """Send a signed welcome event after Supabase has authenticated the new user."""
    if not settings.n8n_customer_registered_webhook_url or not settings.n8n_webhook_secret or not email:
        return False
    event_id = f"customer.registered:{user_id}"
    async with _local_lock:
        if event_id in _local_delivered:
            return True
    envelope = {
        "event_id": event_id,
        "event_type": "customer.registered",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": {"user_id": user_id, "email": email, "name": full_name or "there"},
    }
    payload = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Zarma-Event": "customer.registered",
        "X-Zarma-Event-Id": event_id,
        "X-Zarma-Signature": sign_payload(payload, settings.n8n_webhook_secret),
        "X-Zarma-Webhook-Secret": settings.n8n_webhook_secret,
    }
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                response = await client.post(settings.n8n_customer_registered_webhook_url, content=payload, headers=headers)
            if 200 <= response.status_code < 300:
                async with _local_lock:
                    _local_delivered[event_id] = datetime.now(timezone.utc).timestamp()
                    _local_delivered.move_to_end(event_id)
                    while len(_local_delivered) > _MAX_LOCAL_EVENTS:
                        _local_delivered.popitem(last=False)
                return True
            if 400 <= response.status_code < 500:
                logger.error("n8n_customer_registration_rejected status=%s", response.status_code)
                return False
        except (httpx.HTTPError, TimeoutError) as error:
            logger.warning("n8n_customer_registration_retry error=%s attempt=%s", type(error).__name__, attempt + 1)
        if attempt < 2:
            await asyncio.sleep(0.25 * (2**attempt))
    logger.error("n8n_customer_registration_failed")
    return False
