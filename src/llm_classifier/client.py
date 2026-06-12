from __future__ import annotations

import json
from typing import cast

import boto3  # type: ignore[import-untyped]
import structlog
from anthropic import Anthropic

from src.llm_classifier.catalog import DomainCatalog
from src.llm_classifier.prompts import (
    CACHED_BLOCK,
    DOMAIN_SPECS,
    build_domain_system_prompt,
)
from src.llm_classifier.schemas import Attempt, AttemptClassification
from src.llm_classifier.tools import CLASSIFY_TOOL, build_classify_tool
from src.shared.settings import get_settings

logger = structlog.get_logger()

_MODEL = "claude-haiku-4-5-20251001"


class PausedError(Exception):
    """Raised when SSM killswitch /innova/llm/paused == 'true'."""


def get_ssm_param(param_name: str) -> str:
    """Read SSM parameter. Returns empty string on failure."""
    try:
        settings = get_settings()
        # type: ignore[misc]
        ssm = boto3.client("ssm", region_name=settings.app_aws_region)
        resp: dict[str, object] = ssm.get_parameter(Name=param_name)  # type: ignore[misc]
        param = cast(dict[str, object], resp["Parameter"])
        return str(param["Value"])
    except Exception:
        return ""


def _ensure_not_paused(trace_id: str) -> None:
    settings = get_settings()
    paused = get_ssm_param(settings.ssm_llm_paused_param)
    if paused.lower() == "true":
        logger.warning("llm_paused_by_killswitch", trace_id=trace_id)
        raise PausedError("LLM paused by cost killswitch")


def _user_payload(attempts: list[Attempt]) -> str:
    return json.dumps(
        [
            {
                "attempt_id": a.id,
                "topic": a.topic,
                "subdomain": a.subdomain_code,
                "problem": a.problem_statement,
                "canonical": a.canonical_solution,
                "student_steps": a.raw_steps,
                "student_answer": a.final_answer,
            }
            for a in attempts
        ],
        ensure_ascii=False,
    )


def _invoke(
    system_text: str,
    tool: dict[str, object],
    user_content: str,
) -> list[AttemptClassification]:
    """Single Anthropic call with the cached system block + forced tool_use.
    cache_control ephemeral MUST stay on the system block (CI enforces it)."""
    settings = get_settings()
    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        temperature=0.0,
        system=[
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[tool],  # type: ignore[arg-type]
        tool_choice={"type": "tool", "name": "classify_errors"},
        messages=[{"role": "user", "content": user_content}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "classify_errors":
            # type: ignore[attr-defined]
            raw: dict[str, object] = block.input  # type: ignore[assignment]
            classifications = cast(list[object], raw["classifications"])
            return [AttemptClassification.model_validate(c) for c in classifications]

    raise RuntimeError(
        "LLM did not return tool_use block -- should not happen with forced tool_choice"
    )


def classify_batch(
        attempts: list[Attempt],
        trace_id: str = "") -> list[AttemptClassification]:
    """v7 generic classifier (full taxonomy in one cached prompt). Kept as the
    fallback for attempts without a resolvable domain. Raises PausedError if the
    SSM killswitch is active."""
    _ensure_not_paused(trace_id)
    user = f"Classify these {
        len(attempts)} attempts:\n{
        _user_payload(attempts)}"
    return _invoke(CACHED_BLOCK, CLASSIFY_TOOL, user)


def classify_batch_for_domain(
    attempts: list[Attempt],
    catalog: DomainCatalog,
    trace_id: str = "",
) -> list[AttemptClassification]:
    """v8 — classify a single-domain batch using the domain-specialized prompt and a
    tool whose enum is the domain's ACTIVE catalog. The catalog is fetched by the
    async consumer (asyncpg) and injected here, keeping this sync path DB-free.
    Raises PausedError if the SSM killswitch is active."""
    _ensure_not_paused(trace_id)

    spec = DOMAIN_SPECS.get(catalog.domain_code)
    if spec is None:
        # Unknown domain code -> safety net on the generic v7 prompt.
        logger.warning("unknown_domain_code", domain_code=catalog.domain_code)
        user = f"Classify these {
            len(attempts)} attempts:\n{
            _user_payload(attempts)}"
        return _invoke(CACHED_BLOCK, CLASSIFY_TOOL, user)

    system_text = build_domain_system_prompt(spec, catalog.taxonomy_text)
    tool = build_classify_tool(catalog.error_codes)
    user = (
        f"Classify these {len(attempts)} {catalog.domain_code} attempts:\n"
        f"{_user_payload(attempts)}"
    )
    logger.info(
        "llm_domain_batch",
        domain_code=catalog.domain_code,
        n=len(attempts),
        catalog_hash=catalog.catalog_hash,
        trace_id=trace_id,
    )
    return _invoke(system_text, tool, user)
