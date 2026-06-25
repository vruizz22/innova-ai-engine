from __future__ import annotations

from src.guide_ingest.prompts import (
    EXTRACT_GUIDE_SYSTEM,
    EXTRACT_GUIDE_TOOL,
    build_extract_user_text,
)


def test_tool_name_and_question_schema() -> None:
    assert EXTRACT_GUIDE_TOOL["name"] == "extract_guide"
    item = EXTRACT_GUIDE_TOOL["input_schema"]["properties"]["questions"]["items"]
    props = item["properties"]
    for field in ("statement_latex", "statement_text", "figure_bboxes", "continues_previous"):
        assert field in props
    assert item["required"] == ["statement_latex", "statement_text"]


def test_system_prompt_covers_key_rules() -> None:
    assert "extract_guide" in EXTRACT_GUIDE_SYSTEM
    assert "continues_previous" in EXTRACT_GUIDE_SYSTEM
    assert "figure_bboxes" in EXTRACT_GUIDE_SYSTEM


def test_user_text_includes_grade_and_pages() -> None:
    text = build_extract_user_text(5, 3)
    assert "grade-5" in text
    assert "3 page" in text
