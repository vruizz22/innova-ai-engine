from __future__ import annotations

import asyncio

import structlog

from src.llm_classifier.client import classify_batch
from src.llm_classifier.schemas import Attempt
from src.observability.logging import configure_logging
from src.observability.tracing import bind_trace_id
from src.shared.postgres import get_pool

logger = structlog.get_logger()


def _extract_trace_id(record: dict[str, object]) -> str:
    attrs = record.get("messageAttributes", {})
    if isinstance(attrs, dict):
        trace = attrs.get("trace_id", {})
        if isinstance(trace, dict):
            return str(trace.get("stringValue", ""))
    return ""


async def _main(event: dict[str, object], context: object) -> dict[str, object]:
    configure_logging()

    raw_records = event.get("Records", [])
    records: list[dict[str, object]] = list(raw_records) if isinstance(raw_records, list) else []
    if not records:
        return {"processed": 0}

    trace_id = _extract_trace_id(records[0])
    bind_trace_id(trace_id)

    attempts = [Attempt.model_validate_json(str(r["body"])) for r in records]

    try:
        classifications = classify_batch(attempts, trace_id=trace_id)
    except Exception as exc:
        logger.error("llm_batch_failed", error=str(exc), n=len(attempts))
        raise

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for c in classifications:
                await conn.execute(
                    """
                    UPDATE attempts
                       SET error_type = $1,
                           classifier_source = 'llm',
                           confidence = $2,
                           llm_evidence = $3,
                           classified_at = NOW()
                     WHERE id = $4
                    """,
                    c.error_type,
                    c.confidence,
                    c.evidence,
                    c.attempt_id,
                )

    logger.info("llm_batch_classified", n=len(classifications), trace_id=trace_id)
    return {"processed": len(classifications)}


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    return asyncio.run(_main(event, context))
