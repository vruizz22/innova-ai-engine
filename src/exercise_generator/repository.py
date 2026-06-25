from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol

import structlog

logger = structlog.get_logger()


class WriterConn(Protocol):
    async def execute(self, query: str, *args: object) -> object: ...
    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None: ...
    async def fetch(self, query: str, *args: object) -> Sequence[Mapping[str, object]]: ...


_LOAD_SUBDOMAIN = """
SELECT s.id, s.name AS description
  FROM subdomains s
  JOIN domains d ON d.id = s.domain_id
 WHERE s.code = $1
    OR (d.code || '_' || s.code) = $1
    OR (d.code || ' ' || s.code) = $1
 LIMIT 1
"""

_SUBDOMAIN_FROM_ERROR_CODE = """
SELECT s.id, s.name AS description
  FROM error_tags et
  JOIN subdomains s ON s.code = et.subdomain_code
 WHERE et.code = $1
 LIMIT 1
"""

_TOPIC_FOR_SUBDOMAIN = """
SELECT t.id
  FROM topics t
 WHERE t.subdomain_id = $1
 LIMIT 1
"""

_LOAD_ERROR_DESCRIPTIONS = """
SELECT code, COALESCE(description, name, code) AS description
  FROM error_tags
 WHERE code = ANY($1)
"""

# Returns only error tag ids/codes that actually exist — used to filter the
# LLM's output before inserting FK links (never creates new error tags).
_LOOKUP_ERROR_TAG_IDS = """
SELECT id, code
  FROM error_tags
 WHERE code = ANY($1)
"""

_PROBLEM_EXISTS = """
SELECT 1
  FROM exercises e
  JOIN topics t ON t.id = e.topic_id
 WHERE t.subdomain_id = $1
   AND (e.content->>'prompt' = $2 OR e.content->>'problem_latex' = $2)
 LIMIT 1
"""

# exercises.created_at defaults to NOW(); there is no updated_at column.
_INSERT_EXERCISE = """
INSERT INTO exercises
    (id, topic_id, source, content, irt_a, irt_b, status)
VALUES (
    gen_random_uuid(),
    $1,
    'LLM_GENERATED',
    $2::jsonb,
    $3,
    $4,
    'ACTIVE'
)
RETURNING id
"""

# Links an exercise to the error tags it targets. Uses only IDs that already
# exist in error_tags — never inserts new tags.
_INSERT_EXERCISE_ERROR_TAGS = """
INSERT INTO "_ExerciseTargetErrors" ("A", "B")
SELECT et.id, $1
  FROM error_tags et
 WHERE et.code = ANY($2)
ON CONFLICT DO NOTHING
"""

_SAVE_COST = """
INSERT INTO cost_events
       (id, worker, model, input_tokens, output_tokens,
        cache_creation_input_tokens, cache_read_input_tokens,
        cost_usd, trace_id, created_at)
VALUES (gen_random_uuid()::text, $1, $2, $3, $4, $5, $6, $7, $8, NOW())
"""


class AsyncpgExerciseRepository:
    """`ExerciseRepositoryPort` against Supabase Postgres (CLAUDE.md §10)."""

    def __init__(self, conn: WriterConn) -> None:
        self._conn = conn

    async def load_subdomain(self, subdomain_code: str) -> tuple[str, str] | None:
        row = await self._conn.fetchrow(_LOAD_SUBDOMAIN, subdomain_code)
        if row is None:
            return None
        return str(row["id"]), str(row["description"])

    async def load_subdomain_for_error_code(self, error_code: str) -> tuple[str, str] | None:
        row = await self._conn.fetchrow(_SUBDOMAIN_FROM_ERROR_CODE, error_code)
        if row is None:
            return None
        return str(row["id"]), str(row["description"])

    async def load_error_descriptions(self, error_codes: list[str]) -> dict[str, str]:
        rows = await self._conn.fetch(_LOAD_ERROR_DESCRIPTIONS, error_codes)
        return {str(r["code"]): str(r["description"]) for r in rows}

    async def topic_id_for_subdomain(self, subdomain_id: str) -> str | None:
        row = await self._conn.fetchrow(_TOPIC_FOR_SUBDOMAIN, subdomain_id)
        if row is None:
            return None
        return str(row["id"])

    async def problem_exists(self, problem_latex: str, subdomain_id: str) -> bool:
        row = await self._conn.fetchrow(_PROBLEM_EXISTS, subdomain_id, problem_latex)
        return row is not None

    async def persist_exercise(
        self,
        *,
        topic_id: str,
        problem_latex: str,
        correct_answer_latex: str,
        solution_steps_latex: list[str],
        irt_a: float,
        irt_b: float,
        target_error_codes: list[str],
    ) -> str:
        content = json.dumps(
            {
                "prompt": problem_latex,
                "correct_answer_latex": correct_answer_latex,
                "solution_steps_latex": solution_steps_latex,
                "target_error_codes": target_error_codes,
            }
        )
        row = await self._conn.fetchrow(_INSERT_EXERCISE, topic_id, content, irt_a, irt_b)
        if row is None:
            raise RuntimeError("INSERT exercise returned no row")
        exercise_id = str(row["id"])

        # Link to existing error tags (lookup only — never creates new tags).
        if target_error_codes:
            await self._conn.execute(_INSERT_EXERCISE_ERROR_TAGS, exercise_id, target_error_codes)

        return exercise_id

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
        except Exception:
            logger.warning("exercise_generator.cost_event_failed", trace_id=trace_id)
