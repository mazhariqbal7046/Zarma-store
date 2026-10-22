import pytest

from app.main import app
from app.settings import settings
from conftest import SyncASGIClient


client = SyncASGIClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "zarma-store-api"}


def test_docs_and_openapi_endpoints() -> None:
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "Swagger UI" in docs.text

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    document = openapi.json()
    assert document["info"]["title"] == "Zarma Store API"
    assert "/health" in document["paths"]
    assert "/api/v1/me" in document["paths"]
    assert "/api/v1/ai/search" in document["paths"]
    assert "/api/v1/ai/chat" in document["paths"]
    assert "/api/v1/ai/outfit" in document["paths"]
    assert "/api/v1/ai/conversations/{conversation_id}" in document["paths"]


def test_protected_endpoint_rejects_missing_token() -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer session required"


def test_invalid_request_returns_validation_error() -> None:
    response = client.post("/api/v1/ai/search", json={})
    assert response.status_code == 422


def test_missing_payment_provider_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jazzcash_merchant_id", "")
    monkeypatch.setattr(settings, "jazzcash_callback_secret", "")
    event = {
        "payment_id": "payment-test",
        "provider_event_id": "event-test",
        "event_type": "payment",
        "status": "paid",
        "payload": {},
        "signature": "x" * 16,
    }
    response = client.post("/api/v1/payments/jazzcash/callback", json=event)
    assert response.status_code == 503
    assert "credentials" in response.json()["detail"]
