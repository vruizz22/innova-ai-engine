from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.llm_classifier.catalog import DomainCatalog
from src.llm_classifier.schemas import Attempt


def _fract_catalog() -> DomainCatalog:
    return DomainCatalog(
        domain_id="dom-fract",
        domain_code="FRACT",
        domain_name="Fractions",
        error_codes=["FRACT_MUL_CROSS_MULTIPLIES_G6"],
        taxonomy_text=(
            "[ERROR CATALOG -- domain: Fractions]\n"
            "- FRACT_MUL_CROSS_MULTIPLIES_G6: cross multiplies"
        ),
        catalog_hash="abc123def456",
    )


def _build_mock_tool_response(
    error_type: str = "BORROW_OMITTED_TENS",
    confidence: float = 0.9,
    n: int = 20,
) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "classify_errors"
    block.input = {
        "classifications": [
            {
                "attempt_id": f"att-{i}",
                "error_type": error_type,
                "evidence": "test evidence",
                "confidence": confidence,
            }
            for i in range(n)
        ]
    }
    response = MagicMock()
    response.content = [block]
    return response


def _build_attempts(n: int = 20) -> list[Attempt]:
    return [
        Attempt(
            id=f"att-{i}",
            topic="subtraction_borrow",
            problem_statement="53 - 26",
            canonical_solution="27",
            raw_steps=[],
            final_answer="33",
        )
        for i in range(n)
    ]


def test_cache_control_present_in_system_prompt() -> None:
    """cache_control: {"type": "ephemeral"} MUST be on the system message content block."""
    with patch("src.llm_classifier.client.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _build_mock_tool_response()

        from src.llm_classifier.client import classify_batch

        with patch("src.llm_classifier.client.get_ssm_param", return_value="false"):
            classify_batch(attempts=_build_attempts(20), trace_id="test-trace")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        system_block = call_kwargs["system"][0]
        assert system_block.get("cache_control") == {"type": "ephemeral"}, (
            "cache_control MUST be set on system prompt block"
        )


def test_tool_choice_forced() -> None:
    """tool_choice must be {"type": "tool", "name": "classify_errors"} -- never auto."""
    with patch("src.llm_classifier.client.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _build_mock_tool_response()

        from src.llm_classifier.client import classify_batch

        with patch("src.llm_classifier.client.get_ssm_param", return_value="false"):
            classify_batch(attempts=_build_attempts(20), trace_id="test-trace")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "classify_errors"}


def test_tool_use_response_parsed_correctly() -> None:
    """Response with tool_use block must parse to list[AttemptClassification]."""
    from src.llm_classifier.batch import parse_tool_use_response

    mock_response = _build_mock_tool_response(
        error_type="BORROW_OMITTED_TENS", confidence=0.9, n=20
    )
    results = parse_tool_use_response(mock_response)
    assert len(results) == 20
    assert all(r.error_type == "BORROW_OMITTED_TENS" for r in results)
    assert all(0.0 <= r.confidence <= 1.0 for r in results)


def test_killswitch_drops_to_dlq() -> None:
    """When SSM paused=true, must raise PausedError and not call Anthropic API."""
    with patch("src.llm_classifier.client.get_ssm_param", return_value="true"):
        with patch("src.llm_classifier.client.Anthropic") as mock_anthropic:
            from src.llm_classifier.client import PausedError, classify_batch

            with pytest.raises(PausedError):
                classify_batch(attempts=_build_attempts(20), trace_id="test")

            mock_anthropic.return_value.messages.create.assert_not_called()


def test_classify_batch_for_domain_uses_domain_prompt_and_scoped_enum() -> None:
    """v8 by-domain path: domain-specialized cached prompt + tool enum limited to the
    domain catalog (+ specials)."""
    with patch("src.llm_classifier.client.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _build_mock_tool_response(
            error_type="FRACT_MUL_CROSS_MULTIPLIES_G6", n=1
        )

        from src.llm_classifier.client import classify_batch_for_domain

        with patch("src.llm_classifier.client.get_ssm_param", return_value="false"):
            results = classify_batch_for_domain(_build_attempts(1), _fract_catalog(), trace_id="t")

        kw = mock_client.messages.create.call_args.kwargs
        system_block = kw["system"][0]
        assert system_block["cache_control"] == {"type": "ephemeral"}
        assert "Fractions" in system_block["text"]
        assert "FRACT_MUL_CROSS_MULTIPLIES_G6" in system_block["text"]
        assert kw["tool_choice"] == {"type": "tool", "name": "classify_errors"}

        enum_vals = kw["tools"][0]["input_schema"]["properties"]["classifications"]["items"][
            "properties"
        ]["error_type"]["enum"]
        assert "FRACT_MUL_CROSS_MULTIPLIES_G6" in enum_vals
        assert "CORRECT" in enum_vals
        assert "BORROW_OMITTED_TENS" not in enum_vals
        assert len(results) == 1


def test_classify_batch_for_domain_killswitch() -> None:
    with patch("src.llm_classifier.client.get_ssm_param", return_value="true"):
        with patch("src.llm_classifier.client.Anthropic") as mock_anthropic:
            from src.llm_classifier.client import PausedError, classify_batch_for_domain

            with pytest.raises(PausedError):
                classify_batch_for_domain(_build_attempts(1), _fract_catalog(), trace_id="t")

            mock_anthropic.return_value.messages.create.assert_not_called()
