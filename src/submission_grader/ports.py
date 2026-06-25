from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.observability.cost import TokenUsage
from src.submission_grader.schemas import SubmissionContext, TranscribeAndAlign


class GraderResponseError(RuntimeError):
    """The grader's LLM response could not be parsed into a valid `TranscribeAndAlign`
    (unparseable tool payload or missing forced-tool block).

    Non-retryable by design: the model is deterministic at temperature 0, so re-calling
    it with the same photos yields the same malformed output while re-billing the vision
    call. The service must close the submission as FAILED instead of letting SQS redeliver
    it — otherwise a single unreadable photo loops forever and burns money."""


@runtime_checkable
class SubmissionGraderPort(Protocol):
    """Haiku 4.5 vision: transcribe the photos + align against the pauta (one call),
    returning the call's token usage so the service can price the submission (A9.4)."""

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
    ) -> tuple[TranscribeAndAlign, TokenUsage]: ...


@runtime_checkable
class SubmissionRepositoryPort(Protocol):
    """asyncpg access for A8 (CLAUDE.md §10, async)."""

    async def load_submission_context(self, guide_submission_id: str) -> SubmissionContext | None:
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
        """Persist one LLM cost event for the admin cost dashboard (A9.4/C2).
        Implementations must swallow errors — cost events are observability-only
        and must never block the main grading flow."""
        ...
