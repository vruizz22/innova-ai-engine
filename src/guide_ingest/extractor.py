from __future__ import annotations

import base64

import structlog
from anthropic import AsyncAnthropic

from src.guide_ingest.prompts import (
    EXTRACT_GUIDE_SYSTEM,
    EXTRACT_GUIDE_TOOL,
    build_extract_user_text,
)
from src.guide_ingest.schemas import ExtractGuideResult
from src.shared.killswitch import ensure_not_paused
from src.shared.settings import get_settings

logger = structlog.get_logger()

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 8192


class SonnetExtractor:
    """`GuideExtractorPort` via Sonnet 4.6. Sends the PDF chunk as a native document
    content block, forces the `extract_guide` tool, and keeps the system prompt cached
    (cache_control: ephemeral) — required by CLAUDE.md §6 / §13."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._paused_param = settings.ssm_guides_ingest_paused_param

    async def extract_chunk(
            self,
            pdf_chunk: bytes,
            *,
            grade_level: int,
            page_count: int,
            trace_id: str = "") -> ExtractGuideResult:
        ensure_not_paused(self._paused_param, trace_id=trace_id)
        encoded = base64.standard_b64encode(pdf_chunk).decode("ascii")
        user_content: list[dict[str, object]] = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": encoded,
                },
            },
            {"type": "text", "text": build_extract_user_text(grade_level, page_count)},
        ]
        response = await self._client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0.0,
            system=[
                {
                    "type": "text",
                    "text": EXTRACT_GUIDE_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[EXTRACT_GUIDE_TOOL],  # type: ignore[arg-type]
            tool_choice={"type": "tool", "name": "extract_guide"},
            # type: ignore[arg-type]
            messages=[{"role": "user", "content": user_content}],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "extract_guide":
                result = ExtractGuideResult.model_validate(block.input)
                logger.info(
                    "guide_extract_chunk_done",
                    questions=len(result.questions),
                    page_count=page_count,
                    trace_id=trace_id,
                )
                return result

        raise RuntimeError(
            "extractor returned no extract_guide tool_use block (forced tool_choice)"
        )
