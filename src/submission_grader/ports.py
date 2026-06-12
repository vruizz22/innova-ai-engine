from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.submission_grader.schemas import SubmissionContext, TranscribeAndAlign


@runtime_checkable
class SubmissionGraderPort(Protocol):
    """Haiku 4.5 vision: transcribe the photos + align against the pauta (one call)."""

    async def grade(
        self,
        images: list[bytes],
        *,
        grade_level: int,
        question_label: str | None,
        solution_steps_json: str,
        solution_final_answer: str,
        domain_catalog_text: str,
        trace_id: str = "",
    ) -> TranscribeAndAlign: ...


@runtime_checkable
class SubmissionRepositoryPort(Protocol):
    """asyncpg access for A8 (CLAUDE.md §10, async)."""

    async def load_submission_context(
        self, guide_submission_id: str
    ) -> SubmissionContext | None:
        """Load the submission + its question's current pauta + domain catalog extract.
        Returns None when the submission or its current solution is missing."""
        ...

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
    ) -> None: ...
