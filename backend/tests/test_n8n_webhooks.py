import asyncio
from uuid import uuid4

import httpx

from app import n8n_webhooks
from app.settings import settings


def test_signature_is_hmac_sha256():
    assert n8n_webhooks.sign_payload(b'{"ok":true}', "secret").startswith("sha256=")


def test_order_webhook_is_signed_and_deduplicated(monkeypatch):
    previous_url, previous_secret = settings.n8n_order_webhook_url, settings.n8n_webhook_secret
    calls = []
    order_id = str(uuid4())

    async def fake_send(payload, event_id):
        calls.append((payload, event_id))
        return httpx.Response(204)

    try:
        settings.n8n_order_webhook_url = "https://n8n.example/webhook/order"
        settings.n8n_webhook_secret = "test-secret"
        monkeypatch.setattr(n8n_webhooks, "_send_once", fake_send)
        order = {"id": order_id, "status": "pending", "total_pkr": 1000}
        assert asyncio.run(n8n_webhooks.deliver_new_order(order, "user-1")) is True
        assert asyncio.run(n8n_webhooks.deliver_new_order(order, "user-1")) is True
        assert len(calls) == 1
        assert calls[0][1] == f"order.created:{order_id}"
        assert b"order.created" in calls[0][0]
    finally:
        settings.n8n_order_webhook_url, settings.n8n_webhook_secret = previous_url, previous_secret


def test_order_webhook_retries_transient_failure(monkeypatch):
    previous_url, previous_secret = settings.n8n_order_webhook_url, settings.n8n_webhook_secret
    statuses = iter((httpx.Response(503), httpx.Response(204)))
    order_id = str(uuid4())

    async def fake_send(payload, event_id):
        return next(statuses)

    try:
        settings.n8n_order_webhook_url = "https://n8n.example/webhook/order"
        settings.n8n_webhook_secret = "test-secret"
        monkeypatch.setattr(n8n_webhooks, "_send_once", fake_send)
        assert asyncio.run(n8n_webhooks.deliver_new_order({"id": order_id}, "user-1")) is True
    finally:
        settings.n8n_order_webhook_url, settings.n8n_webhook_secret = previous_url, previous_secret


def test_customer_registration_requires_secret(monkeypatch):
    previous_url, previous_secret = settings.n8n_customer_registered_webhook_url, settings.n8n_webhook_secret
    try:
        settings.n8n_customer_registered_webhook_url = "https://n8n.example/webhook-test/registration"
        settings.n8n_webhook_secret = ""
        assert asyncio.run(n8n_webhooks.deliver_customer_registered("user-1", "test@example.com", "Test User")) is False
    finally:
        settings.n8n_customer_registered_webhook_url, settings.n8n_webhook_secret = previous_url, previous_secret


def test_customer_registration_sends_signed_event(monkeypatch):
    previous_url, previous_secret = settings.n8n_customer_registered_webhook_url, settings.n8n_webhook_secret
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, *, content, headers):
            calls.append((url, content, headers))
            return httpx.Response(204)

    try:
        settings.n8n_customer_registered_webhook_url = "https://n8n.example/webhook-test/registration"
        settings.n8n_webhook_secret = "test-secret"
        monkeypatch.setattr(n8n_webhooks.httpx, "AsyncClient", FakeClient)
        assert asyncio.run(n8n_webhooks.deliver_customer_registered("user-2", "test2@example.com", "Test User")) is True
        assert len(calls) == 1
        assert calls[0][2]["X-Zarma-Event"] == "customer.registered"
        assert b"test2@example.com" in calls[0][1]
    finally:
        settings.n8n_customer_registered_webhook_url, settings.n8n_webhook_secret = previous_url, previous_secret
