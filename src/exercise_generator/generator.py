from __future__ import annotations

import structlog
from anthropic import AsyncAnthropic
from pydantic import ValidationError

from src.exercise_generator.prompts import (
    GENERATE_EXERCISES_TOOL,
    GENERATE_SYSTEM,
    build_generate_user_text,
)
from src.exercise_generator.schemas import GeneratedExercise, GenerateExercisesTool
from src.observability.cost import TokenUsage, usage_from_response
from src.shared.settings import get_settings

logger = structlog.get_logger()

_MODEL = "claude-haiku-4-5"
_MAX_TOKENS = 4096


class HaikuExerciseGenerator:
    """`LlmExerciseGeneratorPort` via Haiku 4.5. Forced tool use `generate_exercises`.
    System prompt is marked `cache_control: ephemeral` — all calls from one Lambda
    container share the cached block."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def generate(
        self,
        *,
        subdomain_code: str,
        subdomain_description: str,
        grade_level: int,
        target_error_codes: list[str],
        error_descriptions: list[str],
        count: int,
        trace_id: str = "",
    ) -> tuple[list[GeneratedExercise], TokenUsage]:
        user_text = build_generate_user_text(
            subdomain_code=subdomain_code,
            subdomain_description=subdomain_description,
            grade_level=grade_level,
            target_error_codes=target_error_codes,
            error_descriptions=error_descriptions,
            count=count,
        )

        response = await self._client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=1.0,
            system=[
                {
                    "type": "text",
                    "text": GENERATE_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[GENERATE_EXERCISES_TOOL],  # type: ignore[list-item]
            tool_choice={"type": "tool", "name": "generate_exercises"},
            messages=[{"role": "user", "content": user_text}],
        )

        usage = usage_from_response(response.usage)

        for block in response.content:
            if block.type == "tool_use" and block.name == "generate_exercises":
                try:
                    parsed = GenerateExercisesTool.model_validate(block.input)
                    return parsed.exercises, usage
                except ValidationError:
                    logger.warning(
                        "exercise_generator.parse_error",
                        trace_id=trace_id,
                        raw=str(block.input)[:200],
                    )
                    return [], usage

        logger.warning("exercise_generator.no_tool_use", trace_id=trace_id)
        return [], usage
