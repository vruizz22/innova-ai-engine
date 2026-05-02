from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.ocr.schemas import OcrResult


@runtime_checkable
class MathOCRPort(Protocol):
    async def extract(self, image_bytes: bytes, trace_id: str = "") -> OcrResult: ...
