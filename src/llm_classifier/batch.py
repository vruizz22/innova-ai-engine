from __future__ import annotations

from typing import cast

import structlog

from .client import classify_batch as _classify_batch
from .schemas import Attempt, AttemptClassification

logger = structlog.get_logger()


def parse_tool_use_response(
        mock_response: object) -> list[AttemptClassification]:
    """Parse a tool_use response object into AttemptClassification list."""
    for block in mock_response.content:  # type: ignore[attr-defined]
        # type: ignore[attr-defined]
        if block.type == "tool_use" and block.name == "classify_errors":
            # type: ignore[attr-defined]
            raw = cast(dict[str, object], block.input)
            classifications = cast(list[object], raw["classifications"])
            return [AttemptClassification.model_validate(
                c) for c in classifications]
    return []


def process_batch(
    attempts: list[Attempt],
    trace_id: str = "",
) -> list[AttemptClassification]:
    """Process a batch of attempts through LLM classification."""
    if not attempts:
        return []
    logger.info("llm_batch_start", n=len(attempts), trace_id=trace_id)
    results = _classify_batch(attempts, trace_id=trace_id)
    logger.info("llm_batch_complete", n=len(results), trace_id=trace_id)
    return results
