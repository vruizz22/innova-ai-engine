from __future__ import annotations

import structlog

from ..shared.settings import get_settings
from .claude_adapter import ClaudeAdapter
from .gemini_adapter import GeminiAdapter
from .schemas import OcrResult

logger = structlog.get_logger()


class OcrOrchestrator:
    def __init__(self) -> None:
        self._gemini = GeminiAdapter()
        self._claude = ClaudeAdapter()

    async def extract(
            self,
            image_bytes: bytes,
            trace_id: str = "") -> OcrResult:
        settings = get_settings()
        threshold = settings.ocr_confidence_threshold

        primary = await self._gemini.extract(image_bytes, trace_id=trace_id)
        logger.info(
            "ocr_primary_result",
            provider=primary.provider,
            confidence=primary.overall_confidence,
            trace_id=trace_id,
        )

        if primary.overall_confidence >= threshold:
            return primary

        logger.info(
            "ocr_escalating_to_claude",
            confidence=primary.overall_confidence,
            trace_id=trace_id,
        )
        fallback = await self._claude.extract(image_bytes, trace_id=trace_id)

        if fallback.overall_confidence > primary.overall_confidence:
            return fallback
        return primary
