from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol, cast
from uuid import uuid4

import structlog

from src.llm_classifier.catalog import Fetcher, clear_catalog_cache, get_domain_catalog
from src.llm_classifier.client import classify_batch, classify_batch_for_domain
from src.llm_classifier.schemas import Attempt, AttemptClassification
from src.llm_classifier.suggest import SuggestedTag, suggest_new_error_types
from src.observability.logging import configure_logging
from src.observability.tracing import bind_trace_id
from src.shared.postgres import get_pool

logger = structlog.get_logger()

# v8: resolve LLM error code to ErrorTag FK via subquery.
# Special sentinel values (CORRECT / UNCLASSIFIED / TRANSVERSAL_LIKELY) must NOT resolve
# to a catalog entry even when a seed error_tag with that code exists — the status filter
# on 'ACTIVE' alone is not enough because those codes are seeded as ACTIVE.
# We also update status: UNCLASSIFIED/TRANSVERSAL_LIKELY stay PENDING (need manual or
# second-pass resolution); everything else (including CORRECT with NULL tag) → CLASSIFIED.
_SPECIAL_TYPES = "('CORRECT', 'UNCLASSIFIED', 'TRANSVERSAL_LIKELY')"
_UPDATE_SQL = f"""
UPDATE attempts
   SET error_tag_id = (
           SELECT id FROM error_tags
            WHERE code = $1
              AND status = 'ACTIVE'
              AND code NOT IN {_SPECIAL_TYPES}
       ),
       classifier_source = 'LLM',
       confidence = $2,
       classified_at = NOW(),
       status = CASE
           WHEN $1 IN {_SPECIAL_TYPES} AND $1 <> 'CORRECT' THEN 'PENDING'
           ELSE 'CLASSIFIED'
       END
 WHERE id = $3
"""

# Auto-catalog growth: upsert a new LLM_GENERATED error_tag.
# ON CONFLICT DO UPDATE touches updated_at so RETURNING always yields a row.
# "references" must be quoted — reserved word in PostgreSQL.
_INSERT_TAG_SQL = """
INSERT INTO error_tags (
    id, code, name, description, domain_id,
    source, status, severity,
    applicable_grades, evidence_required, "references",
    diagnostic_hint,
    created_at, updated_at
) VALUES (
    $1, $2, $3, $4, $5,
    'LLM_GENERATED', 'ACTIVE', $6,
    ARRAY[]::int[], ARRAY[]::text[], ARRAY[]::text[],
    $7,
    NOW(), NOW()
)
ON CONFLICT (code) DO UPDATE SET updated_at = NOW()
RETURNING id
"""


class _Conn(Protocol):
    """Structural type for asyncpg connection methods used in this module."""

    async def execute(self, query: str, *args: object) -> str: ...
    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None: ...
    async def fetch(self, query: str, *args: object) -> Sequence[Mapping[str, object]]: ...
    def transaction(self) -> AbstractAsyncContextManager[None]: ...


def _extract_trace_id(record: dict[str, object]) -> str:
    attrs = record.get("messageAttributes")
    if not isinstance(attrs, dict):
        return ""
    trace = cast(dict[str, object], attrs).get("trace_id")
    if not isinstance(trace, dict):
        return ""
    return str(cast(dict[str, object], trace).get("stringValue", ""))


def _group_by_domain(attempts: list[Attempt]) -> dict[str | None, list[Attempt]]:
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
    """Route a same-domain group to the by-domain prompt; fall back to v7 generic
    when the domain is unknown or has no ACTIVE catalog."""
    if domain_id:
        catalog = await get_domain_catalog(conn, domain_id)
        if catalog is not None:
            return classify_batch_for_domain(attempts, catalog, trace_id=trace_id)
        logger.warning("no_active_catalog_for_domain", domain_id=domain_id)
    return classify_batch(attempts, trace_id=trace_id)


async def _suggest_and_assign(
    conn: _Conn,
    unclassified: list[Attempt],
    catalog_text: str,
    trace_id: str,
) -> None:
    """Second-pass for UNCLASSIFIED attempts: propose new error_tag entries and assign.
    Failures are logged and swallowed — the primary classification is already persisted."""
    if not unclassified:
        return

    suggestions = suggest_new_error_types(unclassified, catalog_text, trace_id)
    if not suggestions:
        return

    # Deduplicate by code: one INSERT per unique code.
    seen: set[str] = set()
    unique_tags: list[SuggestedTag] = []
    for s in suggestions:
        if s.code not in seen:
            seen.add(s.code)
            unique_tags.append(s)

    domain_id = next((a.domain_id for a in unclassified if a.domain_id), None)

    async with conn.transaction():
        for tag in unique_tags:
            row = await conn.fetchrow(
                _INSERT_TAG_SQL,
                str(uuid4()),
                tag.code,
                tag.name,
                tag.description,
                domain_id,
                tag.severity,
                tag.diagnostic_hint,
            )
            if row is not None:
                logger.info(
                    "auto_catalog_entry",
                    code=tag.code,
                    name=tag.name,
                    tag_id=str(row["id"]),
                    trace_id=trace_id,
                )

        # Reuse _UPDATE_SQL: the subquery now resolves because the tag was just upserted.
        for s in suggestions:
            await conn.execute(_UPDATE_SQL, s.code, s.confidence, s.attempt_id)

    clear_catalog_cache()
    logger.info(
        "auto_suggest_complete",
        n_unclassified=len(unclassified),
        n_new_tags=len(unique_tags),
        trace_id=trace_id,
    )


async def _main(event: dict[str, object], context: object) -> dict[str, object]:
    configure_logging()

    raw_records = event.get("Records")
    records: list[dict[str, object]] = (
        cast("list[dict[str, object]]", raw_records) if isinstance(raw_records, list) else []
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

        async with cast(_Conn, conn).transaction():
            for c in classifications:
                await cast(_Conn, conn).execute(
                    _UPDATE_SQL, c.error_type, c.confidence, c.attempt_id
                )

        # Second pass: for attempts that the LLM could not classify, propose and
        # persist new error_tag entries so they grow the catalog organically.
        attempt_by_id = {a.id: a for a in attempts}
        unclassified = [
            attempt_by_id[c.attempt_id]
            for c in classifications
            if c.error_type == "UNCLASSIFIED" and c.attempt_id in attempt_by_id
        ]
        if unclassified:
            domain_id_hint = next((a.domain_id for a in unclassified if a.domain_id), None)
            catalog = (
                await get_domain_catalog(cast(Fetcher, conn), domain_id_hint)
                if domain_id_hint
                else None
            )
            catalog_text = catalog.taxonomy_text if catalog else ""
            try:
                await _suggest_and_assign(cast(_Conn, conn), unclassified, catalog_text, trace_id)
            except Exception as exc:
                logger.warning(
                    "auto_suggest_failed",
                    error=str(exc),
                    n=len(unclassified),
                    trace_id=trace_id,
                )

    logger.info("llm_batch_classified", n=len(classifications), trace_id=trace_id)
    return {"processed": len(classifications)}


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    return asyncio.run(_main(event, context))
