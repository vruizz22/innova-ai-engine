from __future__ import annotations

from src.solution_gen.prompts import (
    GENERATE_SOLUTION_SYSTEM,
    GENERATE_SOLUTION_TOOL,
    PROMPT_VERSION,
    build_generate_user_text,
)
from src.solution_gen.schemas import GenerationMode, QuestionToSolve, TopicCandidate


def test_tool_schema_is_forced_shape() -> None:
    assert GENERATE_SOLUTION_TOOL["name"] == "generate_solution"
    schema = GENERATE_SOLUTION_TOOL["input_schema"]
    assert schema["required"] == ["topic_confidence", "final_answer", "steps"]
    props = schema["properties"]
    assert "topic_code" in props
    assert "alt_paths" in props
    assert "matches_provided" in props


def test_system_prompt_versioned_and_mentions_modes() -> None:
    assert PROMPT_VERSION == "9.0"
    assert "# version: 9.0" not in GENERATE_SOLUTION_SYSTEM  # comment lives in source
    for mode in ("VALIDATE", "DERIVE", "FULL"):
        assert mode in GENERATE_SOLUTION_SYSTEM


def test_user_text_carries_mode_grade_and_candidates() -> None:
    question = QuestionToSolve(
        question_id="q1",
        sequence=1,
        label="3.a",
        statement_latex="$2+2$",
        provided_answer="4",
    )
    candidates = [
        TopicCandidate(
            code="ARITH.ADD",
            name="Adición",
            topic_id="t1",
            domain_code="ARITH",
            grade_level=5,
        )
    ]
    text = build_generate_user_text(
        question, GenerationMode.DERIVE, candidates, 5)
    assert "Mode: DERIVE" in text
    assert "Grade level: 5" in text
    assert "3.a" in text
    assert "ARITH.ADD: Adición [ARITH]" in text
    assert "PDF-provided final answer: 4" in text


def test_user_text_handles_no_candidates() -> None:
    question = QuestionToSolve(
        question_id="q1", sequence=1, statement_latex="$x$"
    )
    text = build_generate_user_text(question, GenerationMode.FULL, [], 3)
    assert "set topic_code=null" in text
