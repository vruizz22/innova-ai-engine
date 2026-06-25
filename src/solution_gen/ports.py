from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.solution_gen.schemas import (
    GeneratedSolution,
    GenerationMode,
    GuideContext,
    QuestionToSolve,
    TopicCandidate,
)


@runtime_checkable
class SolutionGeneratorPort(Protocol):
    """LLM that turns one question into a canonical solution + topic classification."""

    async def generate(
        self,
        question: QuestionToSolve,
        *,
        mode: GenerationMode,
        grade_level: int,
        topic_candidates: list[TopicCandidate],
        trace_id: str = "",
    ) -> GeneratedSolution: ...


@runtime_checkable
class SolutionRepositoryPort(Protocol):
    """All Postgres access for A7 (CLAUDE.md §10, async)."""

    async def load_guide_context(
        self, guide_id: str, question_id: str | None = None
    ) -> GuideContext | None:
        """Load the guide + course + the questions to solve. `question_id` narrows to a
        single question (re-generation). Returns None if the guide does not exist."""
        ...

    async def fetch_taxonomy_candidates(self, grade_level: int) -> list[TopicCandidate]:
        """Classification candidates from the error taxonomy (domain/subdomain). Always
        populated, so a question resolves to a real domain even when no curriculum topic
        was seeded for its grade (v9.1, supersedes the topics-table lookup)."""
        ...

    async def fetch_active_error_codes(self, domain_id: str) -> set[str]: ...

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
        """Persist a new current GuideSolution (bumping previous off `is_current`) and
        update the question's status/topic — one transaction."""
        ...

    async def count_unsolved(self, guide_id: str) -> int:
        """Questions in the guide without a current solution yet."""
        ...

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
        """Flip the guide to REVIEW and insert a deduped GUIDE_READY_FOR_REVIEW alert.
        Returns True iff a new alert row was inserted."""
        ...
