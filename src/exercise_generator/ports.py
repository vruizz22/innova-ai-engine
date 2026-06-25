from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.exercise_generator.schemas import GeneratedExercise
from src.observability.cost import TokenUsage


@runtime_checkable
class LlmExerciseGeneratorPort(Protocol):
    """Haiku adapter: produce structured exercises given subdomain + error codes."""

    async def generate(
        self,
        *,
        subdomain_code: str,
        subdomain_description: str,
        grade_level: int,
        target_error_codes: list[str],
        error_descriptions: list[str],
        count: int,
        trace_id: str = "",
    ) -> tuple[list[GeneratedExercise], TokenUsage]: ...


@runtime_checkable
class ExerciseRepositoryPort(Protocol):
    """asyncpg writes for persisting generated exercises."""

    async def load_subdomain(self, subdomain_code: str) -> tuple[str, str] | None:
        """Return (subdomain_id, subdomain_description) or None if not found."""
        ...

    async def load_subdomain_for_error_code(self, error_code: str) -> tuple[str, str] | None:
        """Fallback: look up subdomain via error_tags.subdomain_code when direct
        code lookup fails (handles partial or mistyped subdomain codes)."""
        ...

    async def load_error_descriptions(self, error_codes: list[str]) -> dict[str, str]:
        """Return {error_code: description} for the given codes."""
        ...

    async def topic_id_for_subdomain(self, subdomain_id: str) -> str | None:
        """Return the primary Topic.id for a subdomain (for FK on Exercise)."""
        ...

    async def problem_exists(self, problem_latex: str, subdomain_id: str) -> bool:
        """Deduplicate: True if an exercise with the same LaTeX already exists."""
        ...

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
        """Insert one exercise row; return the new exercise_id."""
        ...

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
    ) -> None: ...


class GeneratorError(Exception):
    """Terminal failure — do not retry (cost guard)."""


class SubdomainNotFoundError(GeneratorError):
    pass
