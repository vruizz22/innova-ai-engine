from __future__ import annotations

import pytest

from src.exercise_generator.ports import GeneratorError, SubdomainNotFoundError
from src.exercise_generator.schemas import (
    GeneratedExercise,
    GenerateExercisesMessage,
)
from src.exercise_generator.service import generate_exercises
from src.observability.cost import TokenUsage

# --- fakes -----------------------------------------------------------------


def _usage() -> TokenUsage:
    return TokenUsage(
        input_tokens=100,
        output_tokens=200,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )


class FakeRepo:
    def __init__(
        self,
        *,
        subdomain: tuple[str, str] | None = ("sd-1", "Fractions"),
        subdomain_by_error: tuple[str, str] | None = None,
        topic_id: str | None = "topic-1",
        error_descriptions: dict[str, str] | None = None,
        problem_exists: bool = False,
        cost_event_raises: bool = False,
    ) -> None:
        self._subdomain = subdomain
        self._subdomain_by_error = subdomain_by_error
        self._topic_id = topic_id
        self._error_descriptions = error_descriptions or {}
        self._problem_exists = problem_exists
        self._cost_event_raises = cost_event_raises
        self.persisted: list[dict[str, object]] = []
        self.cost_events: list[dict[str, object]] = []

    async def load_subdomain(self, subdomain_code: str) -> tuple[str, str] | None:
        return self._subdomain

    async def load_subdomain_for_error_code(self, error_code: str) -> tuple[str, str] | None:
        return self._subdomain_by_error

    async def load_error_descriptions(self, error_codes: list[str]) -> dict[str, str]:
        return {c: self._error_descriptions.get(c, c) for c in error_codes}

    async def topic_id_for_subdomain(self, subdomain_id: str) -> str | None:
        return self._topic_id

    async def problem_exists(self, problem_latex: str, subdomain_id: str) -> bool:
        return self._problem_exists

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
        row = {
            "topic_id": topic_id,
            "problem_latex": problem_latex,
            "irt_a": irt_a,
            "irt_b": irt_b,
        }
        self.persisted.append(row)
        return f"ex-{len(self.persisted)}"

    async def save_cost_event(self, **kwargs: object) -> None:
        if self._cost_event_raises:
            raise RuntimeError("DB error")
        self.cost_events.append(dict(kwargs))


def _exercise(problem: str = "2 + 2", b: float = 0.0) -> GeneratedExercise:
    return GeneratedExercise(
        problem_latex=problem,
        correct_answer_latex="4",
        solution_steps_latex=["2 + 2 = 4"],
        irt_a=1.0,
        irt_b=b,
        target_error_codes=["ARITH_CARRY"],
    )


class FakeGenerator:
    def __init__(
        self,
        exercises: list[GeneratedExercise] | None = None,
    ) -> None:
        self._exercises = [_exercise()] if exercises is None else exercises

    async def generate(self, **_kwargs: object) -> tuple[list[GeneratedExercise], TokenUsage]:
        return self._exercises, _usage()


def _msg(
    count: int = 1,
    target_error_codes: list[str] | None = None,
) -> GenerateExercisesMessage:
    return GenerateExercisesMessage(
        subdomain_code="ARITH_ADD",
        grade_level=5,
        target_error_codes=target_error_codes
        if target_error_codes is not None
        else ["ARITH_CARRY"],
        count=count,
        trace_id="tr-1",
    )


# --- tests ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_persists_one_exercise() -> None:
    repo = FakeRepo()
    gen = FakeGenerator([_exercise("3 + 5")])
    result = await generate_exercises(_msg(), generator=gen, repo=repo)
    assert result.persisted == 1
    assert result.generated == 1
    assert result.subdomain_code == "ARITH_ADD"
    assert len(repo.persisted) == 1
    assert repo.persisted[0]["problem_latex"] == "3 + 5"


@pytest.mark.asyncio
async def test_dedup_skips_existing_problem() -> None:
    repo = FakeRepo(problem_exists=True)
    gen = FakeGenerator([_exercise()])
    result = await generate_exercises(_msg(), generator=gen, repo=repo)
    assert result.generated == 1
    assert result.persisted == 0
    assert len(repo.persisted) == 0


@pytest.mark.asyncio
async def test_subdomain_not_found_raises_terminal() -> None:
    repo = FakeRepo(subdomain=None, subdomain_by_error=None)
    gen = FakeGenerator()
    with pytest.raises(SubdomainNotFoundError):
        await generate_exercises(_msg(), generator=gen, repo=repo)


@pytest.mark.asyncio
async def test_subdomain_resolved_via_error_code_fallback() -> None:
    """When subdomain_code is wrong (e.g. ALGEBRA_EQ_LIN), the service falls
    back to load_subdomain_for_error_code using the first target error code."""
    repo = FakeRepo(subdomain=None, subdomain_by_error=("sd-fallback", "Ecuaciones lineales"))
    gen = FakeGenerator([_exercise()])
    result = await generate_exercises(
        _msg(target_error_codes=["ALGEBRA_EQ_LIN_REFLEXIVE_PROP_FAIL_G7"]),
        generator=gen,
        repo=repo,
    )
    assert result.persisted == 1


@pytest.mark.asyncio
async def test_no_topic_raises_terminal() -> None:
    repo = FakeRepo(topic_id=None)
    gen = FakeGenerator()
    with pytest.raises(GeneratorError):
        await generate_exercises(_msg(), generator=gen, repo=repo)


@pytest.mark.asyncio
async def test_empty_generator_output() -> None:
    repo = FakeRepo()
    gen = FakeGenerator([])
    result = await generate_exercises(_msg(count=3), generator=gen, repo=repo)
    assert result.generated == 0
    assert result.persisted == 0
    assert result.requested == 3


@pytest.mark.asyncio
async def test_cost_event_failure_does_not_propagate() -> None:
    repo = FakeRepo(cost_event_raises=True)
    gen = FakeGenerator([_exercise()])
    result = await generate_exercises(_msg(), generator=gen, repo=repo)
    assert result.persisted == 1


@pytest.mark.asyncio
async def test_multiple_exercises_all_persisted() -> None:
    exercises = [_exercise(f"ex {i}", b=float(i) * 0.3) for i in range(5)]
    repo = FakeRepo()
    gen = FakeGenerator(exercises)
    result = await generate_exercises(_msg(count=5), generator=gen, repo=repo)
    assert result.persisted == 5
    assert len(repo.persisted) == 5


@pytest.mark.asyncio
async def test_cost_event_recorded() -> None:
    repo = FakeRepo()
    gen = FakeGenerator([_exercise()])
    await generate_exercises(_msg(), generator=gen, repo=repo)
    assert len(repo.cost_events) == 1
    ev = repo.cost_events[0]
    assert ev["worker"] == "exercise_generator"
    assert ev["model"] == "claude-haiku-4-5"
    assert isinstance(ev["cost_usd"], float)
