from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


def _build_attempt_body() -> str:
    return json.dumps(
        {
            "id": str(uuid4()),
            "topic": "subtraction_borrow",
            "problem_statement": "53 - 26",
            "canonical_solution": "27",
            "raw_steps": [],
            "final_answer": "33",
            "student_id": str(uuid4()),
        }
    )


def _build_sqs_event(n: int = 20) -> dict[str, object]:
    return {
        "Records": [
            {
                "messageId": str(uuid4()),
                "body": _build_attempt_body(),
                "messageAttributes": {
                    "trace_id": {"stringValue": "test-trace-001", "dataType": "String"},
                },
            }
            for _ in range(n)
        ]
    }


def _build_classification(attempt_id: str = "att-0") -> object:
    from src.llm_classifier.schemas import AttemptClassification

    return AttemptClassification(
        attempt_id=attempt_id,
        error_type="BORROW_OMITTED_TENS",
        evidence="test",
        confidence=0.9,
    )


def _make_mock_pool() -> MagicMock:
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=tx_cm)

    mock_pool = MagicMock()

    @asynccontextmanager  # type: ignore[arg-type]
    async def _acquire() -> object:  # type: ignore[misc]
        yield mock_conn

    mock_pool.acquire = _acquire
    return mock_pool


def test_llm_consumer_processes_batch() -> None:
    event = _build_sqs_event(20)
    mock_cls = [_build_classification(f"att-{i}") for i in range(20)]

    with patch("src.pipeline.llm_consumer.classify_batch", return_value=mock_cls):
        mock_pool = _make_mock_pool()
        with patch("src.pipeline.llm_consumer.get_pool", return_value=mock_pool):
            from src.pipeline.llm_consumer import handler

            result = handler(event, MagicMock())
            assert result["processed"] == 20


def test_trace_id_propagated_from_sqs_attributes() -> None:
    event = _build_sqs_event(1)
    mock_cls = [_build_classification("att-0")]

    with patch("src.pipeline.llm_consumer.classify_batch", return_value=mock_cls):
        mock_pool = _make_mock_pool()
        with patch("src.pipeline.llm_consumer.get_pool", return_value=mock_pool):
            with patch("src.pipeline.llm_consumer.bind_trace_id") as mock_bind:
                from src.pipeline.llm_consumer import handler

                handler(event, MagicMock())
                mock_bind.assert_called_with("test-trace-001")
