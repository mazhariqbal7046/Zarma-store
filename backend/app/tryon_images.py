from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass


ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MIN_IMAGE_DIMENSION = 64
MAX_IMAGE_DIMENSION = 4096


class ImageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedImage:
    content: bytes
    mime_type: str
    width: int
    height: int
    sha256: str


def _jpeg_dimensions(content: bytes) -> tuple[int, int]:
    if not content.startswith(b"\xff\xd8\xff"):
        raise ImageValidationError("Image bytes do not match JPEG content")
    index = 2
    while index + 9 < len(content):
        if content[index] != 0xFF:
            index += 1
            continue
        marker = content[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(content):
            break
        segment_length = struct.unpack_from(">H", content, index)[0]
        if segment_length < 2 or index + segment_length > len(content):
            break
        if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0)):
            if segment_length < 7:
                break
            height, width = struct.unpack_from(">HH", content, index + 3)
            return width, height
        index += segment_length
    raise ImageValidationError("JPEG dimensions could not be read")


def _webp_dimensions(content: bytes) -> tuple[int, int]:
    if len(content) < 30 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        raise ImageValidationError("Image bytes do not match WebP content")
    chunk = content[12:16]
    if chunk == b"VP8X" and len(content) >= 30:
        width = 1 + int.from_bytes(content[24:27], "little")
        height = 1 + int.from_bytes(content[27:30], "little")
        return width, height
    raise ImageValidationError("Only extended WebP dimensions are supported")


def validate_image(content: bytes, mime_type: str) -> ValidatedImage:
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ImageValidationError("Only JPEG, PNG, and WebP images are supported")
    if not content:
        raise ImageValidationError("Image file is empty")
    if len(content) > MAX_IMAGE_BYTES:
        raise ImageValidationError("Source image must be 10 MB or smaller")

    if mime_type == "image/png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n") or len(content) < 24:
            raise ImageValidationError("Image bytes do not match PNG content")
        width, height = struct.unpack_from(">II", content, 16)
    elif mime_type == "image/jpeg":
        width, height = _jpeg_dimensions(content)
    else:
        width, height = _webp_dimensions(content)

    if not (MIN_IMAGE_DIMENSION <= width <= MAX_IMAGE_DIMENSION and MIN_IMAGE_DIMENSION <= height <= MAX_IMAGE_DIMENSION):
        raise ImageValidationError(
            f"Image dimensions must be between {MIN_IMAGE_DIMENSION} and {MAX_IMAGE_DIMENSION} pixels"
        )
    return ValidatedImage(content, mime_type, width, height, hashlib.sha256(content).hexdigest())


def extension_for_mime(mime_type: str) -> str:
    return {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime_type]
