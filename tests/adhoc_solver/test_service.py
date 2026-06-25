from __future__ import annotations

import asyncio

from src.adhoc_solver.schemas import AdhocSolveMessage
from src.adhoc_solver.service import _CORRECT_TAG, _UNKNOWN_TAG, solve_adhoc
from src.shared.settings import Settings
from src.solution_gen.schemas import (
    GeneratedSolution,
    GenerationMode,
    QuestionToSolve,
    SolutionStep,
    TopicCandidate,
)


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "anthropic_api_key": "t",
        "gemini_api_key": "t",
        "solution_topic_min_confidence": 0.85,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def _msg(**over: object) -> AdhocSolveMessage:
    base: dict[str, object] = {
        "attempt_id": "att-1",
        "problem_latex": "2x + 3 = 7",
        "student_steps": ["2x = 4"],
        "student_final_answer": "x = 2",
        "student_id": "stu-1",
        "grade_level": 7,
        "trace_id": "tr-1",
    }
    base.update(over)
    return AdhocSolveMessage(**base)


_CANDIDATE = TopicCandidate(
    code="ALGEBRA/EQ_LINEAR",
    name="Ecuaciones lineales",
    topic_id="t-1",
    domain_id="dom-1",
    subdomain_id="sub-1",
    domain_code="ALGEBRA",
    grade_level=7,
)

_GEN_CORRECT = GeneratedSolution(
    final_answer="x = 2",
    topic_code="ALGEBRA/EQ_LINEAR",
    topic_confidence=0.95,
    steps=[
        SolutionStep(
            latex="2x = 4",
            explanation_es="Resto 3",
            expected_error_tags=["ALGEBRA_SIGN_ERROR"],
        )
    ],
)

_GEN_WRONG = GeneratedSolution(
    final_answer="x = 2",
    topic_code="ALGEBRA/EQ_LINEAR",
    topic_confidence=0.95,
    steps=[
        SolutionStep(
            latex="2x = 4",
            explanation_es="Resto 3",
            expected_error_tags=["ALGEBRA_SIGN_ERROR"],
        )
    ],
)


class _FakeGenerator:
    def __init__(self, result: GeneratedSolution) -> None:
        self._result = result
        self.calls = 0
        self.last_mode: GenerationMode | None = None

    async def generate(
        self,
        question: QuestionToSolve,
        *,
        mode: GenerationMode,
        grade_level: int,
        topic_candidates: list[TopicCandidate],
        trace_id: str = "",
    ) -> GeneratedSolution:
        self.calls += 1
        self.last_mode = mode
        return self._result


class _FakeRepo:
    def __init__(
        self,
        candidates: list[TopicCandidate],
        active_codes: set[str],
        tag_id: str | None = "etag-1",
    ) -> None:
        self._candidates = candidates
        self._active_codes = active_codes
        self._tag_id = tag_id
        self.updated: list[dict[str, object]] = []
        self.failed: list[str] = []

    async def fetch_taxonomy_candidates(self, grade_level: int) -> list[TopicCandidate]:
        return self._candidates

    async def fetch_active_error_codes(self, domain_id: str) -> set[str]:
        return self._active_codes

    async def fetch_error_tag_id(self, code: str) -> str | None:
        return self._tag_id

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
        self.updated.append(
            {
                "attempt_id": attempt_id,
                "is_correct": is_correct,
                "error_tag_id": error_tag_id,
                "derived_answer": derived_answer,
            }
        )

    async def mark_attempt_failed(self, attempt_id: str, *, reason: str) -> None:
        self.failed.append(attempt_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_correct_answer_writes_correct_tag() -> None:
    gen = _FakeGenerator(_GEN_CORRECT)
    repo = _FakeRepo([_CANDIDATE], {"ALGEBRA_SIGN_ERROR"})
    msg = _msg(student_final_answer="x = 2")
    outcome = asyncio.run(solve_adhoc(msg, generator=gen, repo=repo, settings=_settings()))
    assert outcome.is_correct is True
    assert outcome.error_tag_code == _CORRECT_TAG
    assert outcome.status == "CLASSIFIED"
    assert len(repo.updated) == 1
    assert repo.updated[0]["is_correct"] is True


def test_wrong_answer_picks_expected_error_tag() -> None:
    gen = _FakeGenerator(_GEN_WRONG)
    repo = _FakeRepo([_CANDIDATE], {"ALGEBRA_SIGN_ERROR"})
    msg = _msg(student_final_answer="x = 3")  # wrong
    outcome = asyncio.run(solve_adhoc(msg, generator=gen, repo=repo, settings=_settings()))
    assert outcome.is_correct is False
    assert outcome.error_tag_code == "ALGEBRA_SIGN_ERROR"
    assert repo.updated[0]["is_correct"] is False


def test_wrong_answer_falls_back_to_unknown_when_no_allowed_tags() -> None:
    gen = _FakeGenerator(_GEN_WRONG)
    repo = _FakeRepo([_CANDIDATE], set())  # no allowed codes
    msg = _msg(student_final_answer="x = 99")
    outcome = asyncio.run(solve_adhoc(msg, generator=gen, repo=repo, settings=_settings()))
    assert outcome.error_tag_code == _UNKNOWN_TAG


def test_generator_called_in_full_mode() -> None:
    gen = _FakeGenerator(_GEN_CORRECT)
    repo = _FakeRepo([_CANDIDATE], {"ALGEBRA_SIGN_ERROR"})
    asyncio.run(solve_adhoc(_msg(), generator=gen, repo=repo, settings=_settings()))
    assert gen.last_mode == GenerationMode.FULL
    assert gen.calls == 1


def test_no_taxonomy_candidates_marks_failed() -> None:
    gen = _FakeGenerator(_GEN_CORRECT)
    repo = _FakeRepo([], set())
    outcome = asyncio.run(solve_adhoc(_msg(), generator=gen, repo=repo, settings=_settings()))
    assert outcome.status == "FAILED"
    assert "att-1" in repo.failed
    assert gen.calls == 0


def test_unknown_topic_resolves_without_error_tags() -> None:
    """When the generator returns no topic_code, the solver still classifies (no crash)."""
    no_topic_gen = GeneratedSolution(
        final_answer="2",
        topic_code=None,
        topic_confidence=0.0,
        steps=[SolutionStep(latex="step", explanation_es="p")],
    )
    gen = _FakeGenerator(no_topic_gen)
    repo = _FakeRepo([_CANDIDATE], {"SOME_TAG"})
    outcome = asyncio.run(
        solve_adhoc(_msg(student_final_answer="2"), generator=gen, repo=repo, settings=_settings())
    )
    assert outcome.is_correct is True  # "2" matches "2"
    assert outcome.status == "CLASSIFIED"
