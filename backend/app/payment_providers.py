from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.settings import settings


class PaymentProviderUnavailable(RuntimeError):
    pass


class PaymentProviderContractError(RuntimeError):
    pass


def canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def jazzcash_secure_hash(payload: dict[str, Any], shared_secret: str) -> str:
    """JazzCash documented PP-field HMAC-SHA256 calculation."""
    if not shared_secret:
        raise PaymentProviderUnavailable("JazzCash shared secret is not configured")
    values = [
        _text(payload[key])
        for key in sorted(payload)
        if key.startswith("pp_") and key.lower() != "pp_securehash" and payload[key] is not None
    ]
    message = f"{shared_secret}&{'&'.join(values)}"
    message_bytes = message.encode("utf-8").decode("iso-8859-1").encode("iso-8859-1")
    return hmac.new(shared_secret.encode("utf-8"), message_bytes, hashlib.sha256).hexdigest()


def verify_jazzcash_callback(payload: dict[str, Any], signature: str | None = None) -> bool:
    configured = settings.jazzcash_shared_secret or settings.jazzcash_callback_secret
    provided = signature or payload.get("pp_SecureHash") or payload.get("secureHash")
    return bool(provided and hmac.compare_digest(jazzcash_secure_hash(payload, configured).lower(), str(provided).lower()))


def easypaisa_callback_signature(payload: dict[str, Any], secret: str) -> str:
    """Separate Easypaisa callback hook; exact field order remains merchant-contract specific."""
    if not secret:
        raise PaymentProviderUnavailable("Easypaisa callback secret is not configured")
    canonical = "&".join(f"{key}={_text(payload[key])}" for key in sorted(payload) if key not in {"signature", "secureHash"})
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_easypaisa_callback(payload: dict[str, Any], signature: str | None = None) -> bool:
    if not settings.easypaisa_contract_verified:
        raise PaymentProviderUnavailable("Easypaisa live callback is disabled until the assigned merchant contract is verified")
    expected = easypaisa_callback_signature(payload, settings.easypaisa_callback_secret)
    provided = signature or payload.get("signature") or payload.get("secureHash")
    return bool(provided and hmac.compare_digest(expected.lower(), str(provided).lower()))


def provider_config(provider: str) -> tuple[str, str]:
    if provider == "jazzcash":
        return settings.jazzcash_merchant_id, settings.jazzcash_shared_secret or settings.jazzcash_callback_secret
    if provider == "easypaisa":
        return settings.easypaisa_merchant_id, settings.easypaisa_callback_secret
    raise PaymentProviderUnavailable("Unsupported payment provider")


def ensure_provider_configured(provider: str) -> None:
    merchant_id, secret = provider_config(provider)
    if not merchant_id or not secret:
        raise PaymentProviderUnavailable(f"{provider} is disabled until merchant and callback credentials are configured")
    if provider == "jazzcash" and not settings.jazzcash_password:
        raise PaymentProviderUnavailable("JazzCash is disabled until the merchant password is configured")
    if provider == "easypaisa" and not settings.easypaisa_contract_verified:
        raise PaymentProviderUnavailable("Easypaisa is disabled until its assigned merchant API contract is verified")


def verify_callback(provider: str, raw_payload: bytes, signature: str) -> bool:
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if provider == "jazzcash":
        return verify_jazzcash_callback(payload, signature)
    if provider == "easypaisa":
        return verify_easypaisa_callback(payload, signature)
    return False


@dataclass(frozen=True)
class PaymentInitForm:
    action_url: str
    fields: dict[str, str]


class JazzCashAdapter:
    def __init__(self) -> None:
        ensure_provider_configured("jazzcash")

    def build_checkout_form(self, *, amount_pkr: int, transaction_ref: str, bill_reference: str, description: str) -> PaymentInitForm:
        if amount_pkr <= 0:
            raise PaymentProviderContractError("Payment amount must be positive")
        now = datetime.now(timezone.utc)
        fields: dict[str, Any] = {
            "pp_Version": "1.1",
            "pp_TxnType": "MWALLET",
            "pp_Language": "EN",
            "pp_MerchantID": settings.jazzcash_merchant_id,
            "pp_Password": settings.jazzcash_password,
            "pp_TxnRefNo": transaction_ref,
            "pp_Amount": str(amount_pkr),
            "pp_TxnCurrency": "PKR",
            "pp_TxnDateTime": now.strftime("%Y%m%d%H%M%S"),
            "pp_TxnExpiryDateTime": (now + timedelta(minutes=30)).strftime("%Y%m%d%H%M%S"),
            "pp_BillReference": bill_reference,
            "pp_Description": description[:200],
            "pp_ReturnURL": settings.jazzcash_return_url,
        }
        fields["pp_SecureHash"] = jazzcash_secure_hash(fields, settings.jazzcash_shared_secret or settings.jazzcash_callback_secret)
        return PaymentInitForm(settings.jazzcash_checkout_url, {key: _text(value) for key, value in fields.items()})


class EasypaisaAdapter:
    def __init__(self) -> None:
        ensure_provider_configured("easypaisa")
        raise PaymentProviderUnavailable(
            "Easypaisa adapter is intentionally disabled until the merchant-specific official API contract is verified"
        )
