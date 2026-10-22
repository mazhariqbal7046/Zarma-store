from pathlib import Path

from app.api import CheckoutCreate, ProfileUpdate
from app.payment_providers import verify_callback
from app.settings import settings
from app.supabase_rest import SupabaseRestError
from app.tryon_images import ImageValidationError, validate_image


ROOT = Path(__file__).resolve().parents[2]
STEP8_MIGRATION = ROOT / "supabase" / "migrations" / "20261019184057_security_hardening_step8.sql"
CHECKOUT_MIGRATION = ROOT / "supabase" / "migrations" / "20261019184417_security_hardening_step8_checkout.sql"


def test_profile_api_does_not_accept_authorization_fields():
    profile = ProfileUpdate(full_name="Customer", phone="03001234567")
    assert set(ProfileUpdate.model_fields) == {"full_name", "phone"}
    assert not hasattr(profile, "role")
    assert not hasattr(profile, "account_status")


def test_upstream_error_detail_is_sanitized():
    error = SupabaseRestError(500, "database password=do-not-leak")
    assert "do-not-leak" not in error.detail
    assert error.detail == "Upstream service is unavailable"


def test_invalid_image_magic_is_rejected():
    try:
        validate_image(b"not-an-image", "image/png")
    except ImageValidationError:
        pass
    else:
        raise AssertionError("invalid image bytes were accepted")


def test_checkout_input_limits_are_present():
    checkout = CheckoutCreate(
        idempotency_key="order-key-123",
        address_id="00000000-0000-0000-0000-000000000001",
        items=[{"variant_id": "00000000-0000-0000-0000-000000000002", "quantity": 1}],
    )
    assert checkout.items[0].quantity == 1
    assert CheckoutCreate.model_fields["items"].metadata


def test_security_migrations_contain_authorization_guards():
    step8 = STEP8_MIGRATION.read_text(encoding="utf-8")
    checkout = CHECKOUT_MIGRATION.read_text(encoding="utf-8")
    required = (
        "prevent_profile_privilege_escalation",
        "users create own seller applications",
        "users create own customer messages",
        "provider_transaction_id",
        "pp_TxnCurrency",
        "active = true",
    )
    for marker in required:
        assert marker in step8, marker
    assert "Discount must be validated server-side" in checkout
    assert "revoke all on function public.create_order" in checkout


def test_forged_payment_callback_is_rejected():
    previous = settings.jazzcash_callback_secret
    previous_shared = settings.jazzcash_shared_secret
    try:
        settings.jazzcash_callback_secret = "step8-test-secret"
        settings.jazzcash_shared_secret = ""
        assert verify_callback("jazzcash", b"{\"pp_Amount\":\"1000\"}", "forged") is False
    finally:
        settings.jazzcash_callback_secret = previous
        settings.jazzcash_shared_secret = previous_shared
