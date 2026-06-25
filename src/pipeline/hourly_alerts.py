from __future__ import annotations

import asyncio
from typing import cast

import structlog

from src.alerts.repository import AsyncpgAlertRepository, DbConn
from src.alerts.service import run_hourly_alerts
from src.observability.logging import configure_logging
from src.shared.postgres import get_pool
from src.shared.settings import get_settings

logger = structlog.get_logger()


async def _main(event: dict[str, object], context: object) -> dict[str, object]:
    configure_logging()
    settings = get_settings()

    pool = await get_pool()
    async with pool.acquire() as conn:
        repo = AsyncpgAlertRepository(cast(DbConn, conn))
        outcome = await run_hourly_alerts(repo=repo, settings=settings)

    logger.info(
        "hourly_alerts_done",
        candidates=outcome.candidates,
        inserted=outcome.inserted,
        by_type=outcome.by_type,
    )
    return {
        "candidates": outcome.candidates,
        "inserted": outcome.inserted,
        "by_type": outcome.by_type,
    }


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    return asyncio.run(_main(event, context))
