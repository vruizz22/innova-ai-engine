from __future__ import annotations

from unittest.mock import patch

from src.llm_classifier.schemas import Attempt, AttemptClassification


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


def test_process_batch_calls_classify() -> None:
    from src.llm_classifier.batch import process_batch

    mock_results = [
        AttemptClassification(
            attempt_id=f"att-{i}", error_type="BORROW_OMITTED_TENS", evidence="...", confidence=0.9
        )
        for i in range(20)
    ]
    with patch("src.llm_classifier.batch._classify_batch", return_value=mock_results):
        results = process_batch(_build_attempts(20), trace_id="t1")
        assert len(results) == 20


def test_process_batch_empty_returns_empty() -> None:
    from src.llm_classifier.batch import process_batch

    results = process_batch([], trace_id="t1")
    assert results == []
