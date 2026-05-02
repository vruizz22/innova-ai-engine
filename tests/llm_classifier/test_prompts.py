from __future__ import annotations

from src.llm_classifier.prompts import CACHED_BLOCK, ERROR_TAXONOMY, FEW_SHOTS, SYSTEM_PROMPT


def test_cached_block_contains_all_parts() -> None:
    assert SYSTEM_PROMPT in CACHED_BLOCK
    assert ERROR_TAXONOMY in CACHED_BLOCK
    assert FEW_SHOTS in CACHED_BLOCK


def test_system_prompt_not_empty() -> None:
    assert len(SYSTEM_PROMPT) > 100


def test_error_taxonomy_has_mvp_types() -> None:
    assert "BORROW_OMITTED_TENS" in ERROR_TAXONOMY
    assert "SUBTRAHEND_MINUEND_SWAPPED" in ERROR_TAXONOMY
    assert "UNCLASSIFIED" in ERROR_TAXONOMY
