from __future__ import annotations

import asyncio
from typing import cast

import structlog

from src.adhoc_solver.repository import AsyncpgAdhocRepository, DbConn
from src.adhoc_solver.schemas import AdhocSolveMessage
from src.adhoc_solver.service import solve_adhoc
from src.observability.logging import configure_logging
from src.observability.tracing import bind_trace_id
from src.shared.postgres import get_pool
from src.shared.settings import get_settings
from src.solution_gen.generator import SonnetSolutionGenerator

logger = structlog.get_logger()


async def _main(event: dict[str, object], context: object) -> dict[str, object]:
    configure_logging()

    raw_records = event.get("Records")
    records: list[dict[str, object]] = (
        cast("list[dict[str, object]]", raw_records) if isinstance(raw_records, list) else []
    )
    if not records:
        return {"processed": 0, "batchItemFailures": []}

    settings = get_settings()
    generator = SonnetSolutionGenerator()
    pool = await get_pool()
    processed = 0
    failures: list[dict[str, str]] = []

    async with pool.acquire() as conn:
        repo = AsyncpgAdhocRepository(cast(DbConn, conn))
        for record in records:
            message_id = str(record.get("messageId", ""))
            try:
                message = AdhocSolveMessage.model_validate_json(str(record.get("body", "")))
                bind_trace_id(message.trace_id)
                outcome = await solve_adhoc(
                    message,
                    generator=generator,
                    repo=repo,
                    settings=settings,
                )
                logger.info(
                    "adhoc_solve_record_done",
                    attempt_id=outcome.attempt_id,
                    is_correct=outcome.is_correct,
                    status=outcome.status,
                )
                processed += 1
            except Exception as exc:
                failures.append({"itemIdentifier": message_id})
                logger.error(
                    "adhoc_solve_record_failed",
                    error=str(exc),
                    message_id=message_id,
                )

    return {"processed": processed, "batchItemFailures": failures}


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    return asyncio.run(_main(event, context))
