"""Checking images that users upload (Phase 6), before they reach a model or the database.

The browser says what type a file is, but that's only a claim: anyone can send a text file
labelled "image/png". So the type is read from the file's first bytes (its "magic number"),
and anything that isn't a known image format is rejected.
"""

import base64
import binascii

from core.llm import ImagePart

# The first bytes of each format we accept.
SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
}


class ImageError(ValueError):
    """An upload that isn't an acceptable image. The message is safe to show the user."""


def sniff(data: bytes) -> str | None:
    """The real image type of `data`, or None if it isn't a format we accept."""
    for media_type, prefixes in SIGNATURES.items():
        if data.startswith(prefixes):
            return media_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode_image(data_b64: str, *, max_mb: float) -> tuple[bytes, ImagePart]:
    """Base64 from the browser -> (raw bytes, ImagePart with the REAL media type)."""
    try:
        raw = base64.b64decode(data_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageError("The image data is not valid base64.") from exc
    if len(raw) > max_mb * 1024 * 1024:
        raise ImageError(f"Images can be at most {max_mb:g} MB.")
    media_type = sniff(raw)
    if media_type is None:
        raise ImageError("Only PNG, JPEG, WebP and GIF images are supported.")
    return raw, ImagePart(media_type=media_type, data=base64.b64encode(raw).decode())  # type: ignore[arg-type]
