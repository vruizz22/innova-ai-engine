from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.solution_gen.schemas import TopicCandidate


@runtime_checkable
class AdhocRepositoryPort(Protocol):
    """All Postgres access for the adhoc_solver (taxonomy reads + attempt writes)."""

    async def fetch_taxonomy_candidates(self, grade_level: int) -> list[TopicCandidate]:
        """Classification candidates from the error taxonomy for the given grade."""
        ...

    async def fetch_active_error_codes(self, domain_id: str) -> set[str]:
        """Set of ACTIVE error tag codes for a domain (to sanitize LLM-produced tags)."""
        ...

    async def fetch_error_tag_id(self, code: str) -> str | None:
        """Resolve an error tag code to its DB UUID, or None if not found."""
        ...

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
        """Flip the attempt to CLASSIFIED with the derived classification result."""
        ...

    async def mark_attempt_failed(self, attempt_id: str, *, reason: str) -> None:
        """Mark the attempt FAILED when the solver cannot produce a result."""
        ...
