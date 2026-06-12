from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


def _build_attempt_body(domain_id: str | None = None) -> str:
    return json.dumps(
        {
            "id": str(uuid4()),
            "topic": "subtraction_borrow",
            "domain_id": domain_id,
            "subdomain_code": "SUB",
            "problem_statement": "53 - 26",
            "canonical_solution": "27",
            "raw_steps": [],
            "final_answer": "33",
            "student_id": str(uuid4()),
        }
    )


def _record(domain_id: str | None) -> dict[str, object]:
    return {
        "messageId": str(
            uuid4()),
        "body": _build_attempt_body(domain_id),
        "messageAttributes": {
            "trace_id": {
                "stringValue": "test-trace-001",
                "dataType": "String"},
        },
    }


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


def test_llm_consumer_groups_by_domain_and_routes_per_group() -> None:
    """A mixed-domain SQS batch must call the by-domain classifier once per domain,
    and persist one row per attempt."""
    from src.llm_classifier.schemas import Attempt, AttemptClassification

    event = {"Records": [_record("dom-A"), _record("dom-A"), _record("dom-B")]}

    catalog = MagicMock()
    catalog.domain_code = "FRACT"

    def _per_group(
        attempts: list[Attempt], _catalog: object, trace_id: str = ""
    ) -> list[AttemptClassification]:
        return [
            AttemptClassification(
                attempt_id=a.id,
                error_type="FRACT_MUL_CROSS_MULTIPLIES_G6",
                evidence="x",
                confidence=0.9,
            )
            for a in attempts
        ]

    by_domain = MagicMock(side_effect=_per_group)
    generic = MagicMock()

    with patch("src.pipeline.llm_consumer.get_domain_catalog", new=AsyncMock(return_value=catalog)):
        with patch("src.pipeline.llm_consumer.classify_batch_for_domain", new=by_domain):
            with patch("src.pipeline.llm_consumer.classify_batch", new=generic):
                mock_pool = _make_mock_pool()
                with patch("src.pipeline.llm_consumer.get_pool", return_value=mock_pool):
                    from src.pipeline.llm_consumer import handler

                    result = handler(event, MagicMock())

    assert result["processed"] == 3
    assert by_domain.call_count == 2  # one call per distinct domain_id
    generic.assert_not_called()  # every attempt had a resolvable domain


def test_llm_consumer_falls_back_to_generic_when_no_catalog() -> None:
    """domain_id present but no ACTIVE catalog -> v7 generic classifier."""
    from src.llm_classifier.schemas import Attempt, AttemptClassification

    event = {"Records": [_record("dom-empty")]}

    def _generic(
        attempts: list[Attempt], trace_id: str = ""
    ) -> list[AttemptClassification]:
        return [
            AttemptClassification(
                attempt_id=a.id, error_type="UNCLASSIFIED", evidence="x", confidence=0.0
            )
            for a in attempts
        ]

    by_domain = MagicMock()
    generic = MagicMock(side_effect=_generic)

    with patch("src.pipeline.llm_consumer.get_domain_catalog", new=AsyncMock(return_value=None)):
        with patch("src.pipeline.llm_consumer.classify_batch_for_domain", new=by_domain):
            with patch("src.pipeline.llm_consumer.classify_batch", new=generic):
                mock_pool = _make_mock_pool()
                with patch("src.pipeline.llm_consumer.get_pool", return_value=mock_pool):
                    from src.pipeline.llm_consumer import handler

                    result = handler(event, MagicMock())

    assert result["processed"] == 1
    by_domain.assert_not_called()
    generic.assert_called_once()


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
