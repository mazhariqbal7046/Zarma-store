import struct

import pytest

from app.settings import settings
from app.tryon_images import ImageValidationError, validate_image
from app.tryon_provider import GenericTryOnProvider, TryOnProviderUnavailable


def _png(width: int = 64, height: int = 64) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"


def test_tryon_image_validation_checks_magic_bytes_and_dimensions() -> None:
    image = validate_image(_png(), "image/png")
    assert image.width == 64
    assert image.height == 64
    assert len(image.sha256) == 64

    with pytest.raises(ImageValidationError):
        validate_image(b"not-an-image", "image/png")
    with pytest.raises(ImageValidationError):
        validate_image(_png(32, 32), "image/png")


def test_tryon_provider_is_explicitly_unavailable_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tryon_provider_url", "")
    monkeypatch.setattr(settings, "tryon_provider_api_key", "")
    with pytest.raises(TryOnProviderUnavailable, match="live try-on is unavailable"):
        GenericTryOnProvider()


def test_tryon_provider_rejects_non_https_and_external_result_hosts() -> None:
    provider = GenericTryOnProvider("https://provider.example/v1", "test-key")
    with pytest.raises(TryOnProviderUnavailable):
        GenericTryOnProvider("http://provider.example/v1", "test-key")
    with pytest.raises(Exception, match="outside the configured provider host"):
        provider._assert_safe_result_url("https://attacker.example/result.png")


def test_tryon_provider_submission_accepts_documented_shapes() -> None:
    submission = GenericTryOnProvider._submission({"job_id": "provider-1", "status": "processing"})
    assert submission.provider_job_id == "provider-1"
    assert submission.status == "processing"
    immediate = GenericTryOnProvider._submission({"status": "completed", "result_url": "https://provider.example/result.png"})
    assert immediate.result_url.endswith("result.png")
