from __future__ import annotations

from src.llm_classifier.prompts import (
    CACHED_BLOCK,
    DOMAIN_SPECS,
    ERROR_TAXONOMY,
    FEW_SHOTS,
    SYSTEM_PROMPT,
    build_domain_system_prompt,
)


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


def test_domain_specs_cover_17_seeded_domains() -> None:
    expected = {
        "ARITH", "INT", "FRACT", "DEC", "RATIO", "ALGEBRA", "POW", "FUNC",
        "GEOM", "GEOM3D", "TRIG", "STAT", "DATA", "LOG", "SEQ", "COORD", "TRANSV",
    }
    assert set(DOMAIN_SPECS) == expected
    assert all(spec.code == code for code, spec in DOMAIN_SPECS.items())


def test_build_domain_system_prompt_injects_title_and_catalog() -> None:
    spec = DOMAIN_SPECS["FRACT"]
    taxonomy = "[ERROR CATALOG -- domain: Fractions]\n- FRACT_MUL_X_G6: cross multiplies"
    prompt = build_domain_system_prompt(spec, taxonomy)
    assert "Fractions" in prompt
    assert "FRACT_MUL_X_G6" in prompt
    assert "classify_errors" in prompt
    assert "TRANSVERSAL_LIKELY" in prompt
