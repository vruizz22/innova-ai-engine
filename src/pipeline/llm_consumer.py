from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import cast

import structlog

from src.llm_classifier.catalog import Fetcher, get_domain_catalog
from src.llm_classifier.client import classify_batch, classify_batch_for_domain
from src.llm_classifier.schemas import Attempt, AttemptClassification
from src.observability.logging import configure_logging
from src.observability.tracing import bind_trace_id
from src.shared.postgres import get_pool

logger = structlog.get_logger()

# v8: attempts has no `error_type`/`llm_evidence` columns. We resolve the LLM's error
# code to the ErrorTag FK in-query; CORRECT / UNCLASSIFIED / TRANSVERSAL_LIKELY have no
# row, so the subselect yields NULL and error_tag_id is cleared.
_UPDATE_SQL = """
UPDATE attempts
   SET error_tag_id = (SELECT id FROM error_tags WHERE code = $1),
       classifier_source = 'LLM',
       confidence = $2,
       classified_at = NOW()
 WHERE id = $3
"""


def _extract_trace_id(record: dict[str, object]) -> str:
    # isinstance narrows to dict[Unknown, Unknown]; cast back to a typed mapping so
    # .get() stays known under strict (the SQS shape is dict[str, object] in practice).
    attrs = record.get("messageAttributes")
    if not isinstance(attrs, dict):
        return ""
    trace = cast(dict[str, object], attrs).get("trace_id")
    if not isinstance(trace, dict):
        return ""
    return str(cast(dict[str, object], trace).get("stringValue", ""))


def _group_by_domain(attempts: list[Attempt]
                     ) -> dict[str | None, list[Attempt]]:
    """A single SQS batch can mix domains; classify one group per domain (ADR A4.3)."""
    groups: dict[str | None, list[Attempt]] = defaultdict(list)
    for attempt in attempts:
        groups[attempt.domain_id].append(attempt)
    return groups


async def _classify_group(
    conn: Fetcher,
    domain_id: str | None,
    attempts: list[Attempt],
    trace_id: str,
) -> list[AttemptClassification]:
    """Route a same-domain group to the by-domain prompt; fall back to the v7 generic
    classifier when the domain is unknown or has no ACTIVE catalog."""
    if domain_id:
        catalog = await get_domain_catalog(conn, domain_id)
        if catalog is not None:
            return classify_batch_for_domain(
                attempts, catalog, trace_id=trace_id)
        logger.warning("no_active_catalog_for_domain", domain_id=domain_id)
    return classify_batch(attempts, trace_id=trace_id)


async def _main(event: dict[str, object], context: object) -> dict[str, object]:
    configure_logging()

    raw_records = event.get("Records")
    records: list[dict[str, object]] = (
        cast("list[dict[str, object]]", raw_records)
        if isinstance(raw_records, list)
        else []
    )
    if not records:
        return {"processed": 0}

    trace_id = _extract_trace_id(records[0])
    bind_trace_id(trace_id)

    attempts = [Attempt.model_validate_json(str(r["body"])) for r in records]
    groups = _group_by_domain(attempts)

    pool = await get_pool()
    async with pool.acquire() as conn:
        classifications: list[AttemptClassification] = []
        for domain_id, group in groups.items():
            try:
                classifications.extend(
                    # asyncpg is untyped upstream; adapt at this boundary only.
                    await _classify_group(cast(Fetcher, conn), domain_id, group, trace_id)
                )
            except Exception as exc:
                logger.error(
                    "llm_group_failed",
                    error=str(exc),
                    domain_id=domain_id,
                    n=len(group),
                )
                raise

        async with conn.transaction():
            for c in classifications:
                await conn.execute(
                    _UPDATE_SQL,
                    c.error_type,
                    c.confidence,
                    c.attempt_id,
                )

    logger.info("llm_batch_classified", n=len(classifications), trace_id=trace_id)
    return {"processed": len(classifications)}


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    return asyncio.run(_main(event, context))
