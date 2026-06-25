from __future__ import annotations

import pytest

from src.adhoc_solver.domain import answers_match, pick_error_tag
from src.solution_gen.schemas import GeneratedSolution, SolutionStep

# ---------------------------------------------------------------------------
# answers_match
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "derived,student,expected",
    [
        # exact match
        ("2", "2", True),
        # case / space insensitive
        (" 2 ", "2", True),
        # numeric tolerance
        ("2.0", "2", True),
        ("1.0000001", "1", True),
        # fraction
        ("1/2", "0.5", True),
        # LaTeX fraction
        (r"\frac{1}{2}", "0.5", True),
        (r"\frac{1}{2}", "1/2", True),
        # dollar wrap
        ("$2$", "2", True),
        # wrong answer
        ("2", "3", False),
        ("1/2", "1/3", False),
        # variable equation normalisation
        ("x = 2", "x=2", True),
        ("x = 2", "x = 3", False),
        # algebraic strings must match exactly (no numeric parse)
        ("x+1", "x + 1", True),  # strip spaces
        ("x+1", "x+2", False),
    ],
)
def test_answers_match(derived: str, student: str, expected: bool) -> None:
    assert answers_match(derived, student) is expected


# ---------------------------------------------------------------------------
# pick_error_tag
# ---------------------------------------------------------------------------


def _step(tags: list[str]) -> SolutionStep:
    return SolutionStep(
        latex="x=2",
        explanation_es="paso",
        expected_error_tags=tags,
    )


def _gen(steps: list[SolutionStep]) -> GeneratedSolution:
    return GeneratedSolution(
        final_answer="2",
        steps=steps,
        alt_paths=[],
    )


def test_pick_error_tag_returns_first_allowed() -> None:
    gen = _gen([_step(["TAG_A", "TAG_B"]), _step(["TAG_C"])])
    allowed = {"TAG_B", "TAG_C"}
    assert pick_error_tag(gen, allowed) == "TAG_B"


def test_pick_error_tag_skips_disallowed() -> None:
    gen = _gen([_step(["BAD_TAG"]), _step(["GOOD_TAG"])])
    assert pick_error_tag(gen, {"GOOD_TAG"}) == "GOOD_TAG"


def test_pick_error_tag_returns_none_when_empty_allowed() -> None:
    gen = _gen([_step(["TAG_A"])])
    assert pick_error_tag(gen, set()) is None


def test_pick_error_tag_returns_none_when_no_steps() -> None:
    gen = _gen([])
    assert pick_error_tag(gen, {"TAG_A"}) is None
