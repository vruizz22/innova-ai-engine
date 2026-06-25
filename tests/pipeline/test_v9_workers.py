"""Lambda-handler tests for the v9 guide pipeline workers.

The empty/missing-Records paths exercise each handler end-to-end (import wiring +
`asyncio.run` + early return) WITHOUT constructing any LLM/S3/SQS client or touching
the DB — the adapters are only instantiated once there is at least one record.
"""

from __future__ import annotations

import json

import pytest

from src.pipeline import (
    guide_ingest_worker,
    health,
    solution_generator,
    submission_grader,
)

NOOP = {"processed": 0, "batchItemFailures": []}


def test_health_handler_returns_ok() -> None:
    result = health.handler({}, None)
    assert result["statusCode"] == 200
    body = json.loads(str(result["body"]))
    assert body == {"status": "ok", "service": "innova-ai-engine"}


@pytest.mark.parametrize(
    "worker",
    [guide_ingest_worker, solution_generator, submission_grader],
)
@pytest.mark.parametrize("event", [{"Records": []}, {}, {"Records": "nope"}])
def test_worker_noop_without_records(worker: object, event: dict[str, object]) -> None:
    handler = worker.handler
    assert handler(event, None) == NOOP
