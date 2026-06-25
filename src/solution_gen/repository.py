from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from src.solution_gen.schemas import (
    GuideContext,
    QuestionToSolve,
    TopicCandidate,
)


class DbConn(Protocol):
    """The asyncpg connection bits we use (untyped upstream — adapt at the handler)."""

    async def fetch(self, query: str, *args: object) -> Sequence[Mapping[str, object]]: ...

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None: ...

    async def fetchval(self, query: str, *args: object) -> object: ...

    async def execute(self, query: str, *args: object) -> object: ...

    def transaction(self) -> AbstractAsyncContextManager[object]: ...


_GUIDE_HEADER = """
SELECT g.id            AS guide_id,
       g.course_id     AS course_id,
       g.title         AS title,
       g.created_by_teacher_id AS teacher_id,
       g.question_count AS question_count,
       c.subject_id    AS subject_id,
       c.grade_level   AS grade_level
  FROM guides g
  JOIN courses c ON c.id = g.course_id
 WHERE g.id = $1
"""

# Prisma models these ids as `String @id` (text columns, not @db.Uuid), so the
# param is cast to ::text — NOT ::uuid. A ::uuid cast type-checks `q.id = $2::uuid`
# as `text = uuid` at PARSE time (even though the NULL branch never executes at
# runtime) and the whole statement fails with "operator does not exist: text = uuid".
# `$2::text IS NULL` still gives asyncpg a concrete type for the NULL (whole-guide) path.
_GUIDE_QUESTIONS = """
SELECT q.id                       AS question_id,
       q.sequence                 AS sequence,
       q.label                    AS label,
       q.statement_latex          AS statement_latex,
       q.provided_answer          AS provided_answer,
       q.provided_solution_latex  AS provided_solution_latex,
       q.points                   AS points,
       COALESCE(MAX(s.version), 0) AS current_version
  FROM guide_questions q
  LEFT JOIN guide_solutions s ON s.guide_question_id = q.id
 WHERE q.guide_id = $1
   AND ($2::text IS NULL OR q.id = $2::text)
 GROUP BY q.id
 ORDER BY q.sequence
"""

# v9.1: classify against the error TAXONOMY (domain/subdomain), not the sparse,
# hand-seeded `topics` table. domains/subdomains are the same buckets that organize
# the ErrorTag catalog, so every question resolves to a real domain_id (-> ACTIVE
# error codes) regardless of whether a curriculum topic was ever seeded for its grade.
# `code` is qualified (DOMAIN/SUBDOMAIN) so it is globally unique for the LLM to pick;
# `topic_id` is a best-effort link to a curriculum topic when one maps to the subdomain.
_TAXONOMY_CANDIDATES = """
SELECT d.code AS domain_code,
       d.id   AS domain_id,
       s.code AS subdomain_code,
       s.name AS subdomain_name,
       s.id   AS subdomain_id,
       (SELECT t.id FROM topics t WHERE t.subdomain_id = s.id LIMIT 1) AS topic_id
  FROM subdomains s
  JOIN domains d ON d.id = s.domain_id
 ORDER BY d.code, s.code
"""

_ACTIVE_ERROR_CODES = """
SELECT et.code AS code
  FROM error_tags et
 WHERE et.domain_id = $1
   AND et.status = 'ACTIVE'
"""

# Prisma generates DB-side uuids client-side, so raw inserts must supply
# id/updated_at.
_UNFLAG_CURRENT = """
UPDATE guide_solutions
   SET is_current = false
 WHERE guide_question_id = $1 AND is_current = true
"""

_INSERT_SOLUTION = """
INSERT INTO guide_solutions
    (id, guide_question_id, version, is_current, source, final_answer, steps_json,
     solution_latex, expected_error_tags, generated_by_model, prompt_version,
     validation_notes)
VALUES (gen_random_uuid(), $1, $2, true, $3::"SolutionSource", $4, $5::jsonb,
        $6, $7, $8, $9, $10)
"""

_UPDATE_QUESTION = """
UPDATE guide_questions
   SET status = $2::"GuideQuestionStatus",
       topic_id = $3,
       domain_id = $4,
       subdomain_id = $5,
       topic_confidence = $6,
       topic_source = 'LLM',
       updated_at = NOW()
 WHERE id = $1
"""

_COUNT_UNSOLVED = """
SELECT COUNT(*)
  FROM guide_questions q
 WHERE q.guide_id = $1
   AND NOT EXISTS (
       SELECT 1 FROM guide_solutions s
        WHERE s.guide_question_id = q.id AND s.is_current = true)
"""

_MARK_REVIEW = "UPDATE guides SET status = 'REVIEW', updated_at = NOW() WHERE id = $1"

_ALERT_EXISTS = """
SELECT 1
  FROM teacher_alerts
 WHERE alert_type = 'GUIDE_READY_FOR_REVIEW'
   AND resolved_at IS NULL
   AND payload->>'guide_id' = $1
 LIMIT 1
"""

_INSERT_ALERT = """
INSERT INTO teacher_alerts (id, teacher_id, course_id, alert_type, severity, payload)
VALUES (gen_random_uuid(), $1, $2, 'GUIDE_READY_FOR_REVIEW', 'MED', $3::jsonb)
"""


class AsyncpgSolutionRepository:
    """`SolutionRepositoryPort` against the v9 guides tables (CLAUDE.md §10, async)."""

    def __init__(self, conn: DbConn) -> None:
        self._conn = conn

    async def load_guide_context(
        self, guide_id: str, question_id: str | None = None
    ) -> GuideContext | None:
        header = await self._conn.fetchrow(_GUIDE_HEADER, guide_id)
        if header is None:
            return None
        rows = await self._conn.fetch(_GUIDE_QUESTIONS, guide_id, question_id)
        questions = [
            QuestionToSolve(
                question_id=str(row["question_id"]),
                sequence=int(row["sequence"]),  # type: ignore[arg-type]
                label=_opt_str(row["label"]),
                statement_latex=str(row["statement_latex"]),
                provided_answer=_opt_str(row["provided_answer"]),
                provided_solution_latex=_opt_str(row["provided_solution_latex"]),
                points=float(row["points"]),  # type: ignore[arg-type]
                current_version=int(row["current_version"]),  # type: ignore[arg-type]
            )
            for row in rows
        ]
        return GuideContext(
            guide_id=str(header["guide_id"]),
            course_id=str(header["course_id"]),
            subject_id=str(header["subject_id"]),
            grade_level=int(header["grade_level"]),  # type: ignore[arg-type]
            teacher_id=str(header["teacher_id"]),
            title=str(header["title"]),
            question_count=int(header["question_count"]),  # type: ignore[arg-type]
            questions=questions,
        )

    async def fetch_taxonomy_candidates(self, grade_level: int) -> list[TopicCandidate]:
        rows = await self._conn.fetch(_TAXONOMY_CANDIDATES)
        return [
            TopicCandidate(
                code=f"{row['domain_code']}/{row['subdomain_code']}",
                name=str(row["subdomain_name"]),
                topic_id=_opt_str(row["topic_id"]),
                domain_id=_opt_str(row["domain_id"]),
                subdomain_id=_opt_str(row["subdomain_id"]),
                domain_code=_opt_str(row["domain_code"]),
                grade_level=grade_level,
            )
            for row in rows
        ]

    async def fetch_active_error_codes(self, domain_id: str) -> set[str]:
        rows = await self._conn.fetch(_ACTIVE_ERROR_CODES, domain_id)
        return {str(row["code"]) for row in rows}

    async def save_solution(
        self,
        question_id: str,
        *,
        version: int,
        source: str,
        status: str,
        final_answer: str,
        steps_json: str,
        solution_latex: str | None,
        expected_error_tags: list[str],
        topic_id: str | None,
        domain_id: str | None,
        subdomain_id: str | None,
        topic_confidence: float,
        validation_notes: str | None,
        model: str,
        prompt_version: str,
    ) -> None:
        async with self._conn.transaction():
            await self._conn.execute(_UNFLAG_CURRENT, question_id)
            await self._conn.execute(
                _INSERT_SOLUTION,
                question_id,
                version,
                source,
                final_answer,
                steps_json,
                solution_latex,
                expected_error_tags,
                model,
                prompt_version,
                validation_notes,
            )
            await self._conn.execute(
                _UPDATE_QUESTION,
                question_id,
                status,
                topic_id,
                domain_id,
                subdomain_id,
                topic_confidence,
            )

    async def count_unsolved(self, guide_id: str) -> int:
        value = await self._conn.fetchval(_COUNT_UNSOLVED, guide_id)
        return int(value) if value is not None else 0  # type: ignore[arg-type]

    async def mark_guide_review_and_alert(
        self,
        guide_id: str,
        *,
        teacher_id: str,
        course_id: str,
        title: str,
        question_count: int,
        needs_review_count: int,
    ) -> bool:
        async with self._conn.transaction():
            await self._conn.execute(_MARK_REVIEW, guide_id)
            exists = await self._conn.fetchval(_ALERT_EXISTS, guide_id)
            if exists is not None:
                return False
            payload = json.dumps(
                {
                    "guide_id": guide_id,
                    "title": title,
                    "question_count": question_count,
                    "needs_review_count": needs_review_count,
                }
            )
            await self._conn.execute(_INSERT_ALERT, teacher_id, course_id, payload)
            return True


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)
