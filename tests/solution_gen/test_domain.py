from __future__ import annotations

from src.solution_gen.domain import (
    STATUS_OK,
    STATUS_REVIEW,
    collect_error_tags,
    decide_mode,
    grade_window,
    index_candidates,
    resolve_status,
    sanitize_solution,
    solution_source,
)
from src.solution_gen.schemas import (
    GeneratedSolution,
    GenerationMode,
    SolutionStep,
    TopicCandidate,
)


def _gen(**over: object) -> GeneratedSolution:
    base: dict[str, object] = {
        "topic_code": "ARITH.ADD",
        "topic_confidence": 0.95,
        "final_answer": "4",
        "steps": [SolutionStep(latex="2+2", explanation_es="suma")],
    }
    base.update(over)
    return GeneratedSolution(**base)  # type: ignore[arg-type]


def test_decide_mode_picks_validate_then_derive_then_full() -> None:
    assert decide_mode("$x=2$", "2") is GenerationMode.VALIDATE
    assert decide_mode(None, "2") is GenerationMode.DERIVE
    assert decide_mode("   ", "  ") is GenerationMode.FULL
    assert decide_mode(None, None) is GenerationMode.FULL


def test_grade_window_clamps_to_one() -> None:
    assert grade_window(5) == (4, 6)
    assert grade_window(1) == (1, 2)


def test_solution_source_only_validate_is_pdf() -> None:
    assert solution_source(GenerationMode.VALIDATE) == "PDF_PROVIDED"
    assert solution_source(GenerationMode.DERIVE) == "LLM_GENERATED"
    assert solution_source(GenerationMode.FULL) == "LLM_GENERATED"


def test_index_candidates_first_occurrence_wins() -> None:
    a = TopicCandidate(code="T1", name="A", topic_id="ta", grade_level=5)
    b = TopicCandidate(code="T1", name="B", topic_id="tb", grade_level=4)
    index = index_candidates([a, b])
    assert index["T1"].topic_id == "ta"


def test_sanitize_solution_drops_unknown_tags() -> None:
    gen = _gen(
        steps=[
            SolutionStep(
                latex="2+2",
                explanation_es="suma",
                expected_error_tags=["ARITH.CARRY", "HALLUCINATED"],
            )
        ]
    )
    clean = sanitize_solution(gen, {"ARITH.CARRY"})
    assert clean.steps[0].expected_error_tags == ["ARITH.CARRY"]


def test_sanitize_solution_empty_allowed_clears_tags() -> None:
    gen = _gen(steps=[SolutionStep(latex="2+2", explanation_es="suma", expected_error_tags=["X"])])
    clean = sanitize_solution(gen, set())
    assert clean.steps[0].expected_error_tags == []


def test_collect_error_tags_dedupes_and_preserves_order() -> None:
    gen = _gen(
        steps=[
            SolutionStep(latex="a", explanation_es="e", expected_error_tags=["B", "A"]),
            SolutionStep(latex="b", explanation_es="e", expected_error_tags=["A", "C"]),
        ]
    )
    assert collect_error_tags(gen) == ["B", "A", "C"]


def test_resolve_status_ok_for_confident_validate_match() -> None:
    status = resolve_status(
        GenerationMode.VALIDATE,
        _gen(matches_provided=True),
        topic_resolved=True,
        min_topic_confidence=0.85,
    )
    assert status == STATUS_OK


def test_resolve_status_full_always_review() -> None:
    status = resolve_status(
        GenerationMode.FULL,
        _gen(matches_provided=None),
        topic_resolved=True,
        min_topic_confidence=0.85,
    )
    assert status == STATUS_REVIEW


def test_resolve_status_low_confidence_review() -> None:
    status = resolve_status(
        GenerationMode.VALIDATE,
        _gen(topic_confidence=0.5, matches_provided=True),
        topic_resolved=True,
        min_topic_confidence=0.85,
    )
    assert status == STATUS_REVIEW


def test_resolve_status_unresolved_topic_review() -> None:
    status = resolve_status(
        GenerationMode.DERIVE,
        _gen(matches_provided=True),
        topic_resolved=False,
        min_topic_confidence=0.85,
    )
    assert status == STATUS_REVIEW


def test_resolve_status_derive_mismatch_review() -> None:
    status = resolve_status(
        GenerationMode.DERIVE,
        _gen(matches_provided=False),
        topic_resolved=True,
        min_topic_confidence=0.85,
    )
    assert status == STATUS_REVIEW


def test_resolve_status_validation_notes_review() -> None:
    status = resolve_status(
        GenerationMode.VALIDATE,
        _gen(matches_provided=True, validation_notes="discrepa en el paso 2"),
        topic_resolved=True,
        min_topic_confidence=0.85,
    )
    assert status == STATUS_REVIEW
