from __future__ import annotations

import asyncio
import json

import pytest

from src.guide_ingest.schemas import SolutionGenMessage
from src.shared.killswitch import PausedError
from src.shared.settings import Settings
from src.solution_gen.schemas import (
    GeneratedSolution,
    GenerationMode,
    GuideContext,
    QuestionToSolve,
    SolutionStep,
    TopicCandidate,
)
from src.solution_gen.service import generate_solutions


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "anthropic_api_key": "t",
        "gemini_api_key": "t",
        "solution_topic_min_confidence": 0.85,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def _msg(question_id: str | None = None) -> SolutionGenMessage:
    return SolutionGenMessage(guide_id="g1", guide_question_id=question_id, trace_id="tr1")


_CANDIDATE = TopicCandidate(
    code="ARITH.ADD",
    name="Adición",
    topic_id="topic-1",
    domain_id="domain-1",
    subdomain_id="sub-1",
    domain_code="ARITH",
    grade_level=5,
)


class _FakeGenerator:
    def __init__(self, result: GeneratedSolution) -> None:
        self._result = result
        self.calls = 0
        self.modes: list[GenerationMode] = []

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
        self.modes.append(mode)
        return self._result


class _RaisingGenerator:
    async def generate(
        self,
        question: QuestionToSolve,
        *,
        mode: GenerationMode,
        grade_level: int,
        topic_candidates: list[TopicCandidate],
        trace_id: str = "",
    ) -> GeneratedSolution:
        raise PausedError("paused")


class _FakeRepo:
    def __init__(
        self,
        questions: list[QuestionToSolve],
        *,
        unsolved: int = 0,
        active_codes: set[str] | None = None,
    ) -> None:
        self._questions = questions
        self._unsolved = unsolved
        self._active_codes = active_codes or {"ARITH.CARRY"}
        self.saved: list[dict[str, object]] = []
        self.reviewed: list[str] = []

    async def load_guide_context(
        self, guide_id: str, question_id: str | None = None
    ) -> GuideContext | None:
        questions = (
            [q for q in self._questions if q.question_id == question_id]
            if question_id
            else self._questions
        )
        return GuideContext(
            guide_id=guide_id,
            course_id="course-1",
            subject_id="subject-1",
            grade_level=5,
            teacher_id="teacher-1",
            title="Guía 1",
            question_count=len(self._questions),
            questions=questions,
        )

    async def fetch_taxonomy_candidates(self, grade_level: int) -> list[TopicCandidate]:
        return [_CANDIDATE]

    async def fetch_active_error_codes(self, domain_id: str) -> set[str]:
        return self._active_codes

    async def save_solution(self, question_id: str, **kwargs: object) -> None:
        self.saved.append({"question_id": question_id, **kwargs})

    async def count_unsolved(self, guide_id: str) -> int:
        return self._unsolved

    async def mark_guide_review_and_alert(self, guide_id: str, **kwargs: object) -> bool:
        self.reviewed.append(guide_id)
        return True


def _solution(**over: object) -> GeneratedSolution:
    base: dict[str, object] = {
        "topic_code": "ARITH.ADD",
        "topic_confidence": 0.95,
        "final_answer": "4",
        "steps": [SolutionStep(latex="2+2", explanation_es="suma")],
    }
    base.update(over)
    return GeneratedSolution(**base)  # type: ignore[arg-type]


def test_full_question_persists_needs_review_and_keeps_generating() -> None:
    question = QuestionToSolve(question_id="q1", sequence=1, statement_latex="$2+2$")
    generator = _FakeGenerator(_solution(matches_provided=None))
    repo = _FakeRepo([question], unsolved=1)  # other questions still pending

    outcome = asyncio.run(
        generate_solutions(_msg(), generator=generator, repo=repo, settings=_settings())
    )

    assert generator.modes == [GenerationMode.FULL]
    assert outcome.processed == 1
    assert outcome.needs_review_count == 1
    assert outcome.guide_status == "GENERATING_SOLUTIONS"
    assert outcome.alert_created is False
    saved = repo.saved[0]
    assert saved["status"] == "NEEDS_REVIEW"
    assert saved["source"] == "LLM_GENERATED"
    assert saved["version"] == 1
    assert repo.reviewed == []


def test_validate_match_is_extracted_and_pdf_sourced() -> None:
    question = QuestionToSolve(
        question_id="q1",
        sequence=1,
        statement_latex="$2+2$",
        provided_solution_latex="$2+2=4$",
        provided_answer="4",
        current_version=2,
    )
    generator = _FakeGenerator(_solution(matches_provided=True))
    repo = _FakeRepo([question], unsolved=0)

    outcome = asyncio.run(
        generate_solutions(_msg(), generator=generator, repo=repo, settings=_settings())
    )

    assert generator.modes == [GenerationMode.VALIDATE]
    saved = repo.saved[0]
    assert saved["status"] == "EXTRACTED"
    assert saved["source"] == "PDF_PROVIDED"
    assert saved["version"] == 3  # current_version 2 + 1
    assert saved["topic_id"] == "topic-1"
    assert saved["domain_id"] == "domain-1"
    # whole guide solved -> flip to REVIEW + alert
    assert outcome.guide_status == "REVIEW"
    assert outcome.alert_created is True
    assert repo.reviewed == ["g1"]


def test_derive_mismatch_flags_review() -> None:
    question = QuestionToSolve(
        question_id="q1", sequence=1, statement_latex="$2+2$", provided_answer="5"
    )
    generator = _FakeGenerator(
        _solution(matches_provided=False, validation_notes="llega a 4, no a 5")
    )
    repo = _FakeRepo([question], unsolved=0)

    asyncio.run(generate_solutions(_msg(), generator=generator, repo=repo, settings=_settings()))

    assert generator.modes == [GenerationMode.DERIVE]
    assert repo.saved[0]["status"] == "NEEDS_REVIEW"


def test_error_tags_constrained_to_active_catalog() -> None:
    question = QuestionToSolve(question_id="q1", sequence=1, statement_latex="$2+2$")
    generator = _FakeGenerator(
        _solution(
            steps=[
                SolutionStep(
                    latex="2+2",
                    explanation_es="suma",
                    expected_error_tags=["ARITH.CARRY", "HALLUCINATED"],
                )
            ]
        )
    )
    repo = _FakeRepo([question], unsolved=0, active_codes={"ARITH.CARRY"})

    asyncio.run(generate_solutions(_msg(), generator=generator, repo=repo, settings=_settings()))

    assert repo.saved[0]["expected_error_tags"] == ["ARITH.CARRY"]


def test_unresolved_topic_clears_tags_and_flags_review() -> None:
    question = QuestionToSolve(question_id="q1", sequence=1, statement_latex="$2+2$")
    generator = _FakeGenerator(
        _solution(
            topic_code="UNKNOWN.CODE",
            steps=[
                SolutionStep(
                    latex="2+2",
                    explanation_es="suma",
                    expected_error_tags=["ARITH.CARRY"],
                )
            ],
        )
    )
    repo = _FakeRepo([question], unsolved=0)

    asyncio.run(generate_solutions(_msg(), generator=generator, repo=repo, settings=_settings()))

    saved = repo.saved[0]
    assert saved["status"] == "NEEDS_REVIEW"  # topic unresolved
    assert saved["topic_id"] is None
    assert saved["expected_error_tags"] == []  # no domain -> no allowed codes


def test_steps_json_is_canonical_document() -> None:
    question = QuestionToSolve(question_id="q1", sequence=1, statement_latex="$2+2$")
    generator = _FakeGenerator(_solution())
    repo = _FakeRepo([question], unsolved=0)

    asyncio.run(generate_solutions(_msg(), generator=generator, repo=repo, settings=_settings()))

    payload = json.loads(str(repo.saved[0]["steps_json"]))
    assert "steps" in payload and "alt_paths" in payload
    assert payload["steps"][0]["latex"] == "2+2"
    # ADR-118 contract — enforced by both backend canonicalSolutionSchema and the
    # frontend Zod on getGuide; missing any of these breaks the review wizard.
    assert payload["final_answer"] == "4"
    assert payload["points"] == 1.0
    assert payload["steps"][0]["idx"] == 0


def test_killswitch_propagates_and_saves_nothing() -> None:
    question = QuestionToSolve(question_id="q1", sequence=1, statement_latex="$2+2$")
    repo = _FakeRepo([question], unsolved=1)

    with pytest.raises(PausedError):
        asyncio.run(
            generate_solutions(
                _msg(),
                generator=_RaisingGenerator(),
                repo=repo,
                settings=_settings(),
            )
        )

    assert repo.saved == []
    assert repo.reviewed == []


def test_missing_guide_returns_zero() -> None:
    class _EmptyRepo(_FakeRepo):
        async def load_guide_context(
            self, guide_id: str, question_id: str | None = None
        ) -> GuideContext | None:
            return None

    repo = _EmptyRepo([])
    outcome = asyncio.run(
        generate_solutions(
            _msg(), generator=_FakeGenerator(_solution()), repo=repo, settings=_settings()
        )
    )
    assert outcome.processed == 0
    assert repo.saved == []
