from __future__ import annotations

import json
from typing import cast

import boto3  # type: ignore[import-untyped]
import structlog
from anthropic import Anthropic

from ..shared.settings import get_settings
from .prompts import CACHED_BLOCK
from .schemas import Attempt, AttemptClassification
from .tools import CLASSIFY_TOOL

logger = structlog.get_logger()


class PausedError(Exception):
    """Raised when SSM killswitch /innova/llm/paused == 'true'."""


def get_ssm_param(param_name: str) -> str:
    """Read SSM parameter. Returns empty string on failure."""
    try:
        settings = get_settings()
        # type: ignore[misc]
        ssm = boto3.client("ssm", region_name=settings.aws_region)
        resp: dict[str, object] = ssm.get_parameter(
            Name=param_name)  # type: ignore[misc]
        param = cast(dict[str, object], resp["Parameter"])
        return str(param["Value"])
    except Exception:
        return ""


def classify_batch(
        attempts: list[Attempt],
        trace_id: str = "") -> list[AttemptClassification]:
    """
    Single Anthropic API call with prompt caching for up to 20 attempts.
    cache_control ephemeral MUST be set on system prompt block (CI enforces this).
    Raises PausedError if SSM killswitch is active.
    """
    settings = get_settings()
    paused = get_ssm_param(settings.ssm_llm_paused_param)
    if paused.lower() == "true":
        logger.warning("llm_paused_by_killswitch", trace_id=trace_id)
        raise PausedError("LLM paused by cost killswitch")

    user_payload = json.dumps(
        [
            {
                "attempt_id": a.id,
                "topic": a.topic,
                "problem": a.problem_statement,
                "canonical": a.canonical_solution,
                "student_steps": a.raw_steps,
                "student_answer": a.final_answer,
            }
            for a in attempts
        ],
        ensure_ascii=False,
    )

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        temperature=0.0,
        system=[
            {
                "type": "text",
                "text": CACHED_BLOCK,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[CLASSIFY_TOOL],  # type: ignore[arg-type]
        tool_choice={"type": "tool", "name": "classify_errors"},
        messages=[
            {
                "role": "user",
                "content": f"Classify these {len(attempts)} attempts:\n{user_payload}",
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "classify_errors":
            # type: ignore[attr-defined]
            raw: dict[str, object] = block.input  # type: ignore[assignment]
            classifications = cast(list[object], raw["classifications"])
            return [AttemptClassification.model_validate(
                c) for c in classifications]

    raise RuntimeError(
        "LLM did not return tool_use block -- should not happen with forced tool_choice"
    )
