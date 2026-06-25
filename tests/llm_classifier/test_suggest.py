from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.llm_classifier.schemas import Attempt
from src.llm_classifier.suggest import suggest_new_error_types


def _attempt(
    domain_id: str | None = "dom-A",
    subdomain_code: str | None = "ADD",
) -> Attempt:
    return Attempt(
        id=str(uuid4()),
        topic=None,
        domain_id=domain_id,
        subdomain_code=subdomain_code,
        problem_statement="23 + 49",
        canonical_solution="72",
        raw_steps=["20+40=60", "3+9=13", "60+13=74"],
        final_answer="74",
        student_id=str(uuid4()),
    )


def _mock_response(suggestions: list[dict[str, object]]) -> MagicMock:
    """Build a minimal Anthropic response mock with tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "suggest_error_types"
    block.input = {"suggestions": suggestions}

    response = MagicMock()
    response.content = [block]
    return response


def _mock_client(suggestions: list[dict[str, object]]) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = _mock_response(suggestions)
    return client


def test_suggest_returns_empty_for_empty_input() -> None:
    result = suggest_new_error_types([], "", "trace-0")
    assert result == []


def test_suggest_parses_llm_response() -> None:
    attempt = _attempt()
    raw: list[dict[str, object]] = [
        {
            "attempt_id": attempt.id,
            "code": "ADD_WRONG_CARRY_TENS",
            "name": "Acarreo incorrecto en decenas",
            "description": "El alumno propagó el acarreo a la columna incorrecta.",
            "diagnostic_hint": "Revisar posición del acarreo",
            "confidence": 0.85,
            "severity": "MED",
        }
    ]
    with patch("src.llm_classifier.suggest.Anthropic", return_value=_mock_client(raw)):
        with patch(
            "src.llm_classifier.suggest.get_settings", return_value=MagicMock(anthropic_api_key="k")
        ):
            result = suggest_new_error_types([attempt], "", "trace-1")

    assert len(result) == 1
    assert result[0].code == "ADD_WRONG_CARRY_TENS"
    assert result[0].severity == "MED"
    assert result[0].diagnostic_hint == "Revisar posición del acarreo"
    assert result[0].confidence == 0.85
    assert result[0].attempt_id == attempt.id


def test_suggest_multiple_attempts_can_share_code() -> None:
    a1, a2 = _attempt(), _attempt()
    raw: list[dict[str, object]] = [
        {
            "attempt_id": a1.id,
            "code": "ADD_WRONG_CARRY_TENS",
            "name": "Acarreo incorrecto en decenas",
            "description": "Carry to wrong column.",
            "confidence": 0.8,
        },
        {
            "attempt_id": a2.id,
            "code": "ADD_WRONG_CARRY_TENS",
            "name": "Acarreo incorrecto en decenas",
            "description": "Carry to wrong column.",
            "confidence": 0.75,
        },
    ]
    with patch("src.llm_classifier.suggest.Anthropic", return_value=_mock_client(raw)):
        with patch(
            "src.llm_classifier.suggest.get_settings", return_value=MagicMock(anthropic_api_key="k")
        ):
            result = suggest_new_error_types([a1, a2], "", "trace-2")

    assert len(result) == 2
    assert all(r.code == "ADD_WRONG_CARRY_TENS" for r in result)


def test_suggest_system_prompt_has_cache_control() -> None:
    """CI gate: cache_control must be set on the system block (cost constraint)."""
    attempt = _attempt()
    captured: list[Any] = []

    def _fake_create(**kwargs: Any) -> MagicMock:
        captured.append(kwargs)
        return _mock_response(
            [
                {
                    "attempt_id": attempt.id,
                    "code": "X_TEST",
                    "name": "Test",
                    "description": "Desc",
                    "confidence": 0.5,
                }
            ]
        )

    client = MagicMock()
    client.messages.create.side_effect = _fake_create

    with patch("src.llm_classifier.suggest.Anthropic", return_value=client):
        with patch(
            "src.llm_classifier.suggest.get_settings", return_value=MagicMock(anthropic_api_key="k")
        ):
            suggest_new_error_types([attempt], "", "trace-3")

    assert len(captured) == 1
    system = captured[0]["system"]
    assert isinstance(system, list)
    assert len(system) == 1
    assert system[0].get("cache_control") == {"type": "ephemeral"}, (
        "suggest system prompt MUST have cache_control ephemeral (cost constraint)"
    )


def test_suggest_includes_existing_catalog_in_user_content() -> None:
    attempt = _attempt()
    catalog_text = "[ERROR CATALOG -- domain: ARITHMETIC]\n- ADD_CARRY_ERROR: test"
    captured: list[Any] = []

    def _fake_create(**kwargs: Any) -> MagicMock:
        captured.append(kwargs)
        return _mock_response(
            [
                {
                    "attempt_id": attempt.id,
                    "code": "ADD_NEW_ERROR",
                    "name": "New",
                    "description": "Desc",
                    "confidence": 0.7,
                }
            ]
        )

    client = MagicMock()
    client.messages.create.side_effect = _fake_create

    with patch("src.llm_classifier.suggest.Anthropic", return_value=client):
        with patch(
            "src.llm_classifier.suggest.get_settings", return_value=MagicMock(anthropic_api_key="k")
        ):
            suggest_new_error_types([attempt], catalog_text, "trace-4")

    messages = captured[0]["messages"]
    user_content: str = messages[0]["content"]
    assert "ADD_CARRY_ERROR" in user_content, (
        "Existing catalog must be passed to the LLM to avoid code duplication"
    )
