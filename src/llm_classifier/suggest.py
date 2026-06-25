from __future__ import annotations

import json
from typing import Any, Literal, cast

import structlog
from anthropic import Anthropic
from pydantic import BaseModel, Field

from src.llm_classifier.schemas import Attempt
from src.shared.settings import get_settings

logger = structlog.get_logger()

_MODEL = "claude-haiku-4-5-20251001"

_SUGGEST_SYSTEM = """You are an expert in K-12 math education errors \
(elementary school, grades 1-9 in Chile/Latin America).

For student attempts that could NOT be matched against an existing error catalog, \
propose NEW error catalog entries.

Rules for code naming:
- UPPER_SNAKE_CASE, max 60 characters
- Descriptive of the specific procedural mistake (not the topic)
- Prefix with a short domain abbreviation if clear (e.g. FRACT_, ARITH_, ALG_, DEC_)
- Multiple attempts with the same error pattern MUST share ONE code

Rules for fields:
- name: concise Spanish label, max 80 chars (e.g. "Suma de numeradores y denominadores")
- description: pedagogically accurate Spanish description of what the student did wrong, \
max 300 chars
- diagnostic_hint: brief cue to help the teacher identify this error (optional, max 150 chars)
- severity: LOW (minor slip), MED (common teachable error), HIGH (blocks progress)
- confidence: your confidence the proposed description is accurate (0.0-1.0)

Do NOT duplicate existing catalog codes. You may reuse an existing code if the attempt \
clearly matches it."""

SUGGEST_TOOL: dict[str, Any] = {
    "name": "suggest_error_types",
    "description": "Propose new error catalog entries for unclassified student attempts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "suggestions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "attempt_id": {"type": "string"},
                        "code": {
                            "type": "string",
                            "description": "UPPER_SNAKE_CASE error code, max 60 chars",
                            "maxLength": 60,
                        },
                        "name": {"type": "string", "maxLength": 80},
                        "description": {"type": "string", "maxLength": 300},
                        "diagnostic_hint": {"type": "string", "maxLength": 150},
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["LOW", "MED", "HIGH"],
                        },
                    },
                    "required": [
                        "attempt_id",
                        "code",
                        "name",
                        "description",
                        "confidence",
                    ],
                },
            }
        },
        "required": ["suggestions"],
    },
}


class SuggestedTag(BaseModel):
    attempt_id: str
    code: str
    name: str
    description: str
    diagnostic_hint: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    severity: Literal["LOW", "MED", "HIGH"] = "MED"


def _build_user_payload(attempts: list[Attempt], existing_catalog: str) -> str:
    rows = [
        {
            "attempt_id": a.id,
            "topic": a.topic or a.subdomain_code or "",
            "problem": a.problem_statement,
            "canonical": a.canonical_solution,
            "student_steps": a.raw_steps,
            "student_answer": a.final_answer,
        }
        for a in attempts
    ]
    parts = [f"Unclassified attempts ({len(attempts)}):\n{json.dumps(rows, ensure_ascii=False)}"]
    if existing_catalog:
        parts.append(f"\nExisting catalog (do NOT duplicate these codes):\n{existing_catalog}")
    return "\n\n".join(parts)


def suggest_new_error_types(
    attempts: list[Attempt],
    existing_catalog: str,
    trace_id: str = "",
) -> list[SuggestedTag]:
    """Call LLM to propose new error_tag entries for UNCLASSIFIED attempts.
    Multiple attempts may map to the same new code — deduplication is the caller's job.
    Returns [] for empty input without making an API call."""
    if not attempts:
        return []

    settings = get_settings()
    client = Anthropic(api_key=settings.anthropic_api_key)
    user_content = _build_user_payload(attempts, existing_catalog)

    response = client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        temperature=0.0,
        system=[
            {
                "type": "text",
                "text": _SUGGEST_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[SUGGEST_TOOL],  # type: ignore[arg-type]
        tool_choice={"type": "tool", "name": "suggest_error_types"},
        messages=[{"role": "user", "content": user_content}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "suggest_error_types":
            raw: dict[str, object] = block.input  # type: ignore[assignment]
            suggestions = cast(list[object], raw["suggestions"])
            results = [SuggestedTag.model_validate(s) for s in suggestions]
            logger.info(
                "suggest_new_error_types",
                n_attempts=len(attempts),
                n_suggestions=len(results),
                unique_codes=len({s.code for s in results}),
                trace_id=trace_id,
            )
            return results

    raise RuntimeError("LLM did not return tool_use block for suggest_error_types")
