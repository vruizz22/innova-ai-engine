from __future__ import annotations

from src.llm_classifier.tools import CLASSIFY_TOOL, build_classify_tool


def test_tool_name() -> None:
    assert CLASSIFY_TOOL["name"] == "classify_errors"


def test_tool_has_required_input_fields() -> None:
    schema = CLASSIFY_TOOL["input_schema"]
    assert isinstance(schema, dict)
    items_props = schema["properties"]["classifications"]["items"]["properties"]
    assert "attempt_id" in items_props
    assert "error_type" in items_props
    assert "evidence" in items_props
    assert "confidence" in items_props


def test_tool_enum_has_mvp_error_types() -> None:
    schema = CLASSIFY_TOOL["input_schema"]
    enum_vals = schema["properties"]["classifications"]["items"]["properties"]["error_type"]["enum"]
    assert "BORROW_OMITTED_TENS" in enum_vals
    assert "UNCLASSIFIED" in enum_vals
    assert "CORRECT" in enum_vals


def test_build_classify_tool_enum_is_domain_catalog_plus_specials() -> None:
    codes = ["FRACT_MUL_CROSS_MULTIPLIES_G6", "FRACT_DIV_NO_RECIPROCAL_G7"]
    tool = build_classify_tool(codes)
    assert tool["name"] == "classify_errors"
    enum_vals = tool["input_schema"]["properties"]["classifications"]["items"][
        "properties"
    ]["error_type"]["enum"]
    for code in codes:
        assert code in enum_vals
    assert "CORRECT" in enum_vals
    assert "UNCLASSIFIED" in enum_vals
    assert "TRANSVERSAL_LIKELY" in enum_vals
    # v7 codes from a different domain must not leak into a domain-scoped tool.
    assert "BORROW_OMITTED_TENS" not in enum_vals
