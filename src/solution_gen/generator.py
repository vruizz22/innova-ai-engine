from __future__ import annotations

import structlog
from anthropic import AsyncAnthropic

from src.shared.killswitch import ensure_not_paused
from src.shared.settings import get_settings
from src.solution_gen.prompts import (
    GENERATE_SOLUTION_SYSTEM,
    GENERATE_SOLUTION_TOOL,
    build_generate_user_text,
)
from src.solution_gen.schemas import (
    GeneratedSolution,
    GenerationMode,
    QuestionToSolve,
    TopicCandidate,
)

logger = structlog.get_logger()

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 8192


class SonnetSolutionGenerator:
    """`SolutionGeneratorPort` via Sonnet 4.6. Forces the `generate_solution` tool and
    keeps the system prompt cached (cache_control: ephemeral) — CLAUDE.md §6 / §13.

    Works from the extracted `statement_latex` (text-only user turn), not the PDF, so it
    is much cheaper than the A6 extractor."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._paused_param = settings.ssm_guides_solution_paused_param

    async def generate(
        self,
        question: QuestionToSolve,
        *,
        mode: GenerationMode,
        grade_level: int,
        topic_candidates: list[TopicCandidate],
        trace_id: str = "",
    ) -> GeneratedSolution:
        ensure_not_paused(self._paused_param, trace_id=trace_id)
        user_text = build_generate_user_text(
            question, mode, topic_candidates, grade_level
        )
        response = await self._client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0.0,
            system=[
                {
                    "type": "text",
                    "text": GENERATE_SOLUTION_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[GENERATE_SOLUTION_TOOL],  # type: ignore[arg-type]
            tool_choice={"type": "tool", "name": "generate_solution"},
            messages=[{"role": "user", "content": user_text}],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "generate_solution":
                result = GeneratedSolution.model_validate(block.input)
                logger.info(
                    "solution_generated",
                    question_id=question.question_id,
                    mode=mode.value,
                    topic_code=result.topic_code,
                    topic_confidence=result.topic_confidence,
                    steps=len(result.steps),
                    trace_id=trace_id,
                )
                return result

        raise RuntimeError(
            "generator returned no generate_solution tool_use block (forced tool_choice)"
        )
