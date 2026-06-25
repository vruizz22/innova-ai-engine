from __future__ import annotations

import asyncio
from typing import cast

import structlog

from src.guide_ingest.schemas import SolutionGenMessage
from src.observability.logging import configure_logging
from src.observability.tracing import bind_trace_id
from src.shared.killswitch import PausedError
from src.shared.postgres import get_pool
from src.shared.settings import get_settings
from src.solution_gen.generator import SonnetSolutionGenerator
from src.solution_gen.repository import AsyncpgSolutionRepository, DbConn
from src.solution_gen.service import generate_solutions

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
    # SQS partial-batch protocol (functionResponseType:
    # ReportBatchItemFailures).
    failures: list[dict[str, str]] = []

    async with pool.acquire() as conn:
        repo = AsyncpgSolutionRepository(cast(DbConn, conn))
        for record in records:
            message_id = str(record.get("messageId", ""))
            try:
                message = SolutionGenMessage.model_validate_json(str(record.get("body", "")))
                bind_trace_id(message.trace_id)
                outcome = await generate_solutions(
                    message,
                    generator=generator,
                    repo=repo,
                    settings=settings,
                )
                logger.info(
                    "solution_gen_record_done",
                    guide_id=outcome.guide_id,
                    processed=outcome.processed,
                    guide_status=outcome.guide_status,
                    alert_created=outcome.alert_created,
                )
                processed += 1
            except PausedError:
                # Cost killswitch: leave the message for SQS to retry later.
                failures.append({"itemIdentifier": message_id})
                logger.warning("solution_gen_paused", message_id=message_id)
            except Exception as exc:
                failures.append({"itemIdentifier": message_id})
                logger.error("solution_gen_record_failed", error=str(exc), message_id=message_id)

    return {"processed": processed, "batchItemFailures": failures}


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    return asyncio.run(_main(event, context))
