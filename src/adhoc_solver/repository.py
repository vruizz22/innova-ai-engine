from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from src.solution_gen.schemas import TopicCandidate


class DbConn(Protocol):
    async def fetch(self, query: str, *args: object) -> Sequence[Mapping[str, object]]: ...

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None: ...

    async def fetchval(self, query: str, *args: object) -> object: ...

    async def execute(self, query: str, *args: object) -> object: ...

    def transaction(self) -> AbstractAsyncContextManager[object]: ...


# Reuse the same taxonomy query as A7 (same columns, same table)
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
SELECT et.code
  FROM error_tags et
 WHERE et.domain_id = $1
   AND et.status = 'ACTIVE'
"""

_FETCH_ERROR_TAG_ID = """
SELECT id FROM error_tags WHERE code = $1 LIMIT 1
"""

_UPDATE_ATTEMPT_CLASSIFIED = """
UPDATE attempts
   SET status            = 'CLASSIFIED',
       is_correct        = $2,
       error_tag_id      = $3,
       classifier_source = 'LLM',
       classified_at     = NOW(),
       updated_at        = NOW()
 WHERE id = $1
"""

_MARK_ATTEMPT_FAILED = """
UPDATE attempts
   SET status     = 'FAILED',
       updated_at = NOW()
 WHERE id = $1
"""


class AsyncpgAdhocRepository:
    """asyncpg-backed implementation of AdhocRepositoryPort."""

    def __init__(self, conn: DbConn) -> None:
        self._conn = conn

    async def fetch_taxonomy_candidates(self, grade_level: int) -> list[TopicCandidate]:
        rows = await self._conn.fetch(_TAXONOMY_CANDIDATES)
        return [
            TopicCandidate(
                code=f"{r['domain_code']}/{r['subdomain_code']}",
                name=str(r["subdomain_name"]),
                topic_id=str(r["topic_id"]) if r["topic_id"] else None,
                domain_id=str(r["domain_id"]),
                subdomain_id=str(r["subdomain_id"]),
                domain_code=str(r["domain_code"]),
                grade_level=grade_level,
            )
            for r in rows
        ]

    async def fetch_active_error_codes(self, domain_id: str) -> set[str]:
        rows = await self._conn.fetch(_ACTIVE_ERROR_CODES, domain_id)
        return {str(r["code"]) for r in rows}

    async def fetch_error_tag_id(self, code: str) -> str | None:
        val = await self._conn.fetchval(_FETCH_ERROR_TAG_ID, code)
        return str(val) if val is not None else None

    async def update_attempt_classified(
        self,
        attempt_id: str,
        *,
        is_correct: bool,
        error_tag_id: str | None,
        domain_id: str | None,
        subdomain_code: str | None,
        derived_answer: str,
        model: str,
    ) -> None:
        await self._conn.execute(
            _UPDATE_ATTEMPT_CLASSIFIED,
            attempt_id,
            is_correct,
            error_tag_id,
        )

    async def mark_attempt_failed(self, attempt_id: str, *, reason: str) -> None:
        await self._conn.execute(_MARK_ATTEMPT_FAILED, attempt_id)
