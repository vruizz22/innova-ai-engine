from __future__ import annotations

import io

from PIL import Image  # type: ignore[import-untyped]

_MAX_BYTES = 5 * 1024 * 1024


def strip_exif_and_validate(image_bytes: bytes) -> bytes:
    if len(image_bytes) > _MAX_BYTES:
        raise ValueError(f"Image exceeds 5MB limit: {len(image_bytes)} bytes")
    img = Image.open(io.BytesIO(image_bytes))
    output = io.BytesIO()
    img.save(output, format="JPEG", exif=b"")
    return output.getvalue()
