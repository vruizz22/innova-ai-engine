from __future__ import annotations

import asyncio
from typing import cast

import structlog

from src.guide_ingest.publisher import SqsPublisher
from src.guide_ingest.storage import S3ObjectStore
from src.observability.logging import configure_logging
from src.observability.tracing import bind_trace_id
from src.shared.killswitch import PausedError
from src.shared.postgres import get_pool
from src.shared.settings import get_settings
from src.submission_grader.grader import HaikuVisionGrader
from src.submission_grader.repository import AsyncpgSubmissionRepository, DbConn
from src.submission_grader.schemas import GradeSubmissionMessage
from src.submission_grader.service import grade_submission

logger = structlog.get_logger()


async def _main(event: dict[str, object],
                context: object) -> dict[str, object]:
    configure_logging()

    raw_records = event.get("Records")
    records: list[dict[str, object]] = (cast(
        "list[dict[str, object]]", raw_records) if isinstance(raw_records, list) else [])
    if not records:
        return {"processed": 0, "batchItemFailures": []}

    settings = get_settings()
    grader = HaikuVisionGrader()
    store = S3ObjectStore(bucket=settings.s3_submissions_bucket)
    publisher = SqsPublisher()

    pool = await get_pool()
    processed = 0
    # SQS partial-batch protocol (functionResponseType:
    # ReportBatchItemFailures).
    failures: list[dict[str, str]] = []

    async with pool.acquire() as conn:
        repo = AsyncpgSubmissionRepository(cast(DbConn, conn))
        for record in records:
            message_id = str(record.get("messageId", ""))
            try:
                message = GradeSubmissionMessage.model_validate_json(
                    str(record.get("body", ""))
                )
                bind_trace_id(message.trace_id)
                outcome = await grade_submission(
                    message,
                    grader=grader,
                    store=store,
                    publisher=publisher,
                    repo=repo,
                    settings=settings,
                )
                logger.info(
                    "submission_grade_record_done",
                    guide_submission_id=outcome.guide_submission_id,
                    status=outcome.status,
                    published=outcome.published,
                )
                processed += 1
            except PausedError:
                # Cost killswitch: leave the message for SQS to retry later.
                failures.append({"itemIdentifier": message_id})
                logger.warning(
                    "submission_grade_paused",
                    message_id=message_id)
            except Exception as exc:
                failures.append({"itemIdentifier": message_id})
                logger.error(
                    "submission_grade_record_failed",
                    error=str(exc),
                    message_id=message_id,
                )

    return {"processed": processed, "batchItemFailures": failures}


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    return asyncio.run(_main(event, context))
