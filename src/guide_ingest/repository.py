from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

import structlog

from src.guide_ingest.schemas import MergedQuestion

logger = structlog.get_logger()


class WriterConn(Protocol):
    """The asyncpg connection bits we use (untyped upstream — adapt at the handler)."""

    async def execute(self, query: str, *args: object) -> object: ...

    def transaction(self) -> AbstractAsyncContextManager[object]: ...


_MARK_EXTRACTING = "UPDATE guides SET status = 'EXTRACTING', updated_at = NOW() WHERE id = $1"

_MARK_FAILED = """
UPDATE guides
   SET status = 'EXTRACTION_FAILED',
       source_kind = $2,
       source_pdf_pages = $3,
       failure_reason = $4,
       updated_at = NOW()
 WHERE id = $1
"""

# Prisma generates uuids client-side, so raw inserts must supply id + updated_at
# (both NOT NULL with no DB default).
_INSERT_QUESTION = """
INSERT INTO guide_questions
    (id, guide_id, sequence, label, statement_latex, figure_keys,
     provided_answer, provided_solution_latex, updated_at)
VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, NOW())
"""

_COMPLETE_GUIDE = """
UPDATE guides
   SET status = 'GENERATING_SOLUTIONS',
       source_kind = $2,
       source_pdf_pages = $3,
       latex_key = $4,
       extraction_confidence = $5,
       extraction_model = $6,
       question_count = $7,
       updated_at = NOW()
 WHERE id = $1
"""

_SAVE_COST = """
INSERT INTO cost_events
       (id, worker, model, input_tokens, output_tokens,
        cache_creation_input_tokens, cache_read_input_tokens,
        cost_usd, trace_id, created_at)
VALUES (gen_random_uuid()::text, $1, $2, $3, $4, $5, $6, $7, $8, NOW())
"""


class AsyncpgGuideRepository:
    """`GuideRepositoryPort` against `guides` / `guide_questions` (CLAUDE.md §10, async)."""

    def __init__(self, conn: WriterConn) -> None:
        self._conn = conn

    async def mark_extracting(self, guide_id: str) -> None:
        await self._conn.execute(_MARK_EXTRACTING, guide_id)

    async def mark_failed(
        self, guide_id: str, *, source_kind: str, pages: int | None, reason: str
    ) -> None:
        await self._conn.execute(_MARK_FAILED, guide_id, source_kind, pages, reason)

    async def complete(
        self,
        guide_id: str,
        questions: list[MergedQuestion],
        *,
        source_kind: str,
        pages: int | None,
        latex_key: str,
        extraction_confidence: float,
        extraction_model: str,
    ) -> None:
        async with self._conn.transaction():
            for question in questions:
                await self._conn.execute(
                    _INSERT_QUESTION,
                    guide_id,
                    question.sequence,
                    question.label,
                    question.statement_latex,
                    question.figure_keys,
                    question.provided_answer,
                    question.provided_solution_latex,
                )
            await self._conn.execute(
                _COMPLETE_GUIDE,
                guide_id,
                source_kind,
                pages,
                latex_key,
                extraction_confidence,
                extraction_model,
                len(questions),
            )

    async def save_cost_event(
        self,
        *,
        worker: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_input_tokens: int,
        cache_read_input_tokens: int,
        cost_usd: float,
        trace_id: str,
    ) -> None:
        try:
            await self._conn.execute(
                _SAVE_COST,
                worker,
                model,
                input_tokens,
                output_tokens,
                cache_creation_input_tokens,
                cache_read_input_tokens,
                cost_usd,
                trace_id,
            )
        except Exception as exc:
            logger.warning("cost_event_write_failed", error=str(exc), worker=worker)
