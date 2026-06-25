from __future__ import annotations

import base64
from typing import cast

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam
from pydantic import ValidationError

from src.observability.cost import TokenUsage, usage_from_response
from src.shared.killswitch import ensure_not_paused
from src.shared.settings import get_settings
from src.submission_grader.ports import GraderResponseError
from src.submission_grader.prompts import (
    GRADING_SYSTEM,
    TRANSCRIBE_AND_ALIGN_TOOL,
    build_grade_user_text,
    build_pauta_block,
)
from src.submission_grader.schemas import TranscribeAndAlign

logger = structlog.get_logger()

_MODEL = "claude-haiku-4-5"
_MAX_TOKENS = 4096


class HaikuVisionGrader:
    """`SubmissionGraderPort` via Haiku 4.5 vision. One call per submission, forced tool
    `transcribe_and_align`. Two cached (cache_control: ephemeral) system blocks — the
    static grading prompt and the per-question pauta+catalog block, which the ~35
    submissions of a question all share (ADR v9 A8.1, CLAUDE.md §6/§13)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._paused_param = settings.ssm_guides_grading_paused_param

    async def grade(
        self,
        images: list[bytes],
        *,
        grade_level: int,
        question_label: str | None,
        solution_steps_json: str,
        solution_final_answer: str,
        domain_catalog_text: str,
        trace_id: str = "",
    ) -> tuple[TranscribeAndAlign, TokenUsage]:
        ensure_not_paused(self._paused_param, trace_id=trace_id)
        user_content: list[dict[str, object]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(image).decode("ascii"),
                },
            }
            for image in images
        ]
        user_content.append(
            {"type": "text", "text": build_grade_user_text(grade_level, question_label)}
        )
        response = await self._client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0.0,
            system=[
                {
                    "type": "text",
                    "text": GRADING_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": build_pauta_block(
                        solution_steps_json, solution_final_answer, domain_catalog_text
                    ),
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            tools=[TRANSCRIBE_AND_ALIGN_TOOL],  # type: ignore[arg-type]
            tool_choice={"type": "tool", "name": "transcribe_and_align"},
            messages=cast(
                list[MessageParam],
                [{"role": "user", "content": user_content}],
            ),
        )

        usage = usage_from_response(response.usage)
        for block in response.content:
            if block.type == "tool_use" and block.name == "transcribe_and_align":
                try:
                    result = TranscribeAndAlign.model_validate(block.input)
                except ValidationError as exc:
                    # Malformed tool payload (e.g. the model omitted `alignment` /
                    # `provisional`). Non-retryable — surface as a terminal grader error
                    # so the service closes the submission instead of redelivering it.
                    raise GraderResponseError(
                        "grader returned an unparseable transcribe_and_align payload"
                    ) from exc
                logger.info(
                    "submission_graded",
                    images=len(images),
                    confidence=result.transcription.confidence,
                    path=result.alignment.path,
                    score=result.provisional.score_0_1,
                    trace_id=trace_id,
                )
                return result, usage

        raise GraderResponseError(
            "grader returned no transcribe_and_align tool_use block (forced tool_choice)"
        )
