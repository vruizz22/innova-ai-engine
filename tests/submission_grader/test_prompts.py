from __future__ import annotations

from src.submission_grader.prompts import (
    GRADING_SYSTEM,
    PROMPT_VERSION,
    TRANSCRIBE_AND_ALIGN_TOOL,
    build_grade_user_text,
    build_pauta_block,
)


def test_tool_schema_requires_three_sections() -> None:
    assert TRANSCRIBE_AND_ALIGN_TOOL["name"] == "transcribe_and_align"
    required = TRANSCRIBE_AND_ALIGN_TOOL["input_schema"]["required"]
    assert required == ["transcription", "alignment", "provisional"]


def test_system_prompt_versioned_and_no_tag_assignment() -> None:
    assert PROMPT_VERSION == "9.0"
    # ADR-121: the grader must not assign catalog tags.
    assert "Do NOT assign error-catalog tags" in GRADING_SYSTEM


def test_pauta_block_wraps_solution_and_catalog() -> None:
    block = build_pauta_block('{"steps": []}', "42", "ARITH: carry errors")
    assert "<official_solution>" in block
    assert "final_answer: 42" in block
    assert "<error_catalog>" in block
    assert "ARITH: carry errors" in block


def test_user_text_carries_grade_and_label() -> None:
    text = build_grade_user_text(5, "3.a")
    assert "Grade level: 5" in text
    assert "3.a" in text
    # Full-page scan instruction must be present when a label is given.
    assert "ONLY the work for question '3.a'" in text


def test_user_text_without_label() -> None:
    text = build_grade_user_text(4, None)
    assert "Grade level: 4" in text
    assert "ONLY the work for question" not in text
