from __future__ import annotations

import asyncio
from typing import cast

import structlog

from src.exercise_generator.generator import HaikuExerciseGenerator
from src.exercise_generator.ports import GeneratorError
from src.exercise_generator.repository import AsyncpgExerciseRepository, WriterConn
from src.exercise_generator.schemas import GenerateExercisesMessage
from src.exercise_generator.service import generate_exercises
from src.observability.logging import configure_logging
from src.observability.tracing import bind_trace_id
from src.shared.postgres import get_pool

logger = structlog.get_logger()


async def _main(event: dict[str, object], context: object) -> dict[str, object]:
    configure_logging()

    raw_records = event.get("Records")
    records: list[dict[str, object]] = (
        cast("list[dict[str, object]]", raw_records) if isinstance(raw_records, list) else []
    )
    if not records:
        return {"processed": 0, "batchItemFailures": []}

    generator = HaikuExerciseGenerator()
    pool = await get_pool()
    processed = 0
    failures: list[dict[str, str]] = []

    async with pool.acquire() as conn:
        repo = AsyncpgExerciseRepository(cast(WriterConn, conn))
        for record in records:
            message_id = str(record.get("messageId", ""))
            try:
                message = GenerateExercisesMessage.model_validate_json(str(record.get("body", "")))
                bind_trace_id(message.trace_id)
                outcome = await generate_exercises(
                    message,
                    generator=generator,
                    repo=repo,
                )
                logger.info(
                    "exercise_generator_done",
                    subdomain_code=outcome.subdomain_code,
                    requested=outcome.requested,
                    persisted=outcome.persisted,
                )
                processed += 1
            except GeneratorError as exc:
                # Terminal failure (subdomain not found, no topic mapping): do not retry.
                logger.error(
                    "exercise_generator_terminal",
                    error=str(exc),
                    message_id=message_id,
                )
                # Do NOT add to failures — message should be discarded, not retried.
            except Exception as exc:
                failures.append({"itemIdentifier": message_id})
                logger.error(
                    "exercise_generator_failed",
                    error=str(exc),
                    message_id=message_id,
                )

    return {"processed": processed, "batchItemFailures": failures}


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    return asyncio.run(_main(event, context))
