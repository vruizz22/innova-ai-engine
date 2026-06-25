from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, cast

import structlog

from src.llm_classifier.catalog import Fetcher, get_domain_catalog
from src.submission_grader.schemas import SubmissionContext

logger = structlog.get_logger()

# The grader never assigns error tags (ADR-121); it only transcribes, aligns and
# scores. The domain catalog is fed to its prompt solely to anchor prompt caching.
# Once domains carry their full ACTIVE catalog (100-380 tags), the whole taxonomy
# bloats Haiku's prompt and destabilizes its forced tool_use output (it starts
# dropping `alignment`/`provisional`). Cap the extract to a small, fixed budget —
# enough to anchor caching, small enough to keep the small model on-task.
_GRADER_CATALOG_MAX_CHARS = 1500


def _trim_catalog(text: str) -> str:
    """Bound the catalog extract fed to the grader, trimming at a line boundary so
    whole entries survive (the grader uses the catalog for context only, never output)."""
    if len(text) <= _GRADER_CATALOG_MAX_CHARS:
        return text
    cut = text.rfind("\n", 0, _GRADER_CATALOG_MAX_CHARS)
    return text[: cut if cut > 0 else _GRADER_CATALOG_MAX_CHARS] + "\n…(catalog truncated)"


class DbConn(Protocol):
    """The asyncpg connection bits we use (untyped upstream — adapt at the handler)."""

    async def fetch(self, query: str, *args: object) -> Sequence[Mapping[str, object]]: ...

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None: ...

    async def execute(self, query: str, *args: object) -> object: ...


_SUBMISSION_CTX = """
SELECT s.id              AS guide_submission_id,
       s.guide_id        AS guide_id,
       s.guide_question_id AS guide_question_id,
       s.student_id      AS student_id,
       s.attempt_number  AS attempt_number,
       s.photo_keys      AS photo_keys,
       c.grade_level     AS grade_level,
       q.label           AS question_label,
       q.domain_id       AS domain_id
  FROM guide_submissions s
  JOIN guide_questions q ON q.id = s.guide_question_id
  JOIN guides g          ON g.id = s.guide_id
  JOIN courses c         ON c.id = g.course_id
 WHERE s.id = $1
"""

_CURRENT_SOLUTION = """
SELECT version, steps_json, final_answer
  FROM guide_solutions
 WHERE guide_question_id = $1 AND is_current = true
 ORDER BY version DESC
 LIMIT 1
"""

_SAVE_GRADING = """
UPDATE guide_submissions
   SET status = $2::"SubmissionStatus",
       transcription_latex = $3,
       transcription_json = $4::jsonb,
       transcription_confidence = $5,
       alignment_json = $6::jsonb,
       score = $7,
       is_correct = $8,
       solution_version = $9,
       model_used = $10,
       failure_reason = $11,
       graded_at = CASE WHEN $2 = 'GRADED' THEN NOW() ELSE graded_at END,
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


class AsyncpgSubmissionRepository:
    """`SubmissionRepositoryPort` against `guide_submissions` (CLAUDE.md §10, async)."""

    def __init__(self, conn: DbConn) -> None:
        self._conn = conn

    async def load_submission_context(self, guide_submission_id: str) -> SubmissionContext | None:
        row = await self._conn.fetchrow(_SUBMISSION_CTX, guide_submission_id)
        if row is None:
            return None
        question_id = str(row["guide_question_id"])
        solution = await self._conn.fetchrow(_CURRENT_SOLUTION, question_id)
        if solution is None:
            return None  # nothing to grade against — wait for A7 to finish

        domain_id = _opt_str(row["domain_id"])
        catalog_text = ""
        if domain_id is not None:
            catalog = await get_domain_catalog(cast(Fetcher, self._conn), domain_id)
            catalog_text = _trim_catalog(catalog.taxonomy_text) if catalog else ""

        return SubmissionContext(
            guide_submission_id=str(row["guide_submission_id"]),
            guide_id=str(row["guide_id"]),
            guide_question_id=question_id,
            student_id=str(row["student_id"]),
            attempt_number=int(row["attempt_number"]),  # type: ignore[arg-type]
            photo_keys=[str(k) for k in cast(list[object], row["photo_keys"] or [])],
            grade_level=int(row["grade_level"]),  # type: ignore[arg-type]
            question_label=_opt_str(row["question_label"]),
            solution_version=int(solution["version"]),  # type: ignore[arg-type]
            solution_steps_json=str(solution["steps_json"]),
            solution_final_answer=str(solution["final_answer"]),
            domain_id=domain_id,
            domain_catalog_text=catalog_text,
        )

    async def save_grading(
        self,
        guide_submission_id: str,
        *,
        status: str,
        transcription_latex: str,
        transcription_json: str,
        transcription_confidence: float,
        alignment_json: str | None,
        score: float | None,
        is_correct: bool | None,
        solution_version: int,
        model_used: str,
        failure_reason: str | None,
    ) -> None:
        await self._conn.execute(
            _SAVE_GRADING,
            guide_submission_id,
            status,
            transcription_latex,
            transcription_json,
            transcription_confidence,
            alignment_json,
            score,
            is_correct,
            solution_version,
            model_used,
            failure_reason,
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


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)
