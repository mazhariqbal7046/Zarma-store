import pytest

from app.api import PaymentInitiate, RefundCreate, WithdrawalDecision
from app.payment_providers import EasypaisaAdapter, JazzCashAdapter, PaymentProviderUnavailable, jazzcash_secure_hash
from app.settings import settings


def test_jazzcash_official_hash_vector() -> None:
    payload = {"pp_MerchantID": "MER123", "pp_OrderInfo": "A48cvE28", "pp_Amount": "2995"}
    assert jazzcash_secure_hash(payload, "0F5DD14AE2") == "c7689cda7474eb1adcd343fd0c0b676bad0ba66361cc46db589bdb0da4c1c867"


def test_payment_request_rejects_invalid_provider_and_amount() -> None:
    with pytest.raises(ValueError):
        PaymentInitiate(order_id="order", provider="stripe")
    with pytest.raises(ValueError):
        RefundCreate(amount_pkr=0, idempotency_key="refund-key")
    with pytest.raises(ValueError):
        WithdrawalDecision(status="processing", payout_reference="x")


def test_jazzcash_checkout_requires_server_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jazzcash_merchant_id", "")
    monkeypatch.setattr(settings, "jazzcash_password", "")
    monkeypatch.setattr(settings, "jazzcash_callback_secret", "")
    monkeypatch.setattr(settings, "jazzcash_shared_secret", "")
    with pytest.raises(PaymentProviderUnavailable):
        JazzCashAdapter()


def test_easypaisa_live_adapter_requires_verified_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "easypaisa_merchant_id", "merchant")
    monkeypatch.setattr(settings, "easypaisa_callback_secret", "secret")
    monkeypatch.setattr(settings, "easypaisa_contract_verified", False)
    with pytest.raises(PaymentProviderUnavailable, match="contract"):
        EasypaisaAdapter()
