import asyncio

from app.ai_assistant import grounded_assistant_reply
from app.payment_providers import canonical_payload, jazzcash_secure_hash, verify_callback
from app.settings import settings
from app.rate_limit import enforce_rate_limit, _hits


def test_ai_fallback_uses_only_catalog(monkeypatch):
    # Keep this contract test deterministic even when a real Gemini key is configured.
    monkeypatch.setattr("app.ai_assistant.settings.gemini_api_key", "")
    reply, fallback = asyncio.run(grounded_assistant_reply("black shirt", [{"id": "p1", "name": "Black Shirt", "price_pkr": 5000}]))
    assert fallback is True
    assert "Black Shirt" in reply


def test_callback_signature_fixture():
    previous = settings.jazzcash_callback_secret
    previous_shared = settings.jazzcash_shared_secret
    try:
        settings.jazzcash_callback_secret = "0F5DD14AE2"
        settings.jazzcash_shared_secret = ""
        payload = {"pp_MerchantID": "MER123", "pp_OrderInfo": "A48cvE28", "pp_Amount": "2995"}
        signature = jazzcash_secure_hash(payload, "0F5DD14AE2")
        assert verify_callback("jazzcash", canonical_payload(payload), signature) is True
        assert verify_callback("jazzcash", canonical_payload(payload), "invalid-signature") is False
    finally:
        settings.jazzcash_callback_secret = previous
        settings.jazzcash_shared_secret = previous_shared


def test_rate_limit_rejects_after_limit():
    key = "test-rate-limit"
    _hits.pop(key, None)
    for _ in range(2):
        enforce_rate_limit(key, limit=2, window_seconds=60)
    try:
        enforce_rate_limit(key, limit=2, window_seconds=60)
    except Exception as error:
        assert getattr(error, "status_code", None) == 429
    else:
        raise AssertionError("rate limiter did not reject the third request")
