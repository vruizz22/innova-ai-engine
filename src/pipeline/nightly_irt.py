from __future__ import annotations

import asyncio
import uuid

import structlog

from src.irt.two_pl import fit_2pl
from src.observability.logging import configure_logging
from src.observability.tracing import bind_trace_id
from src.shared.postgres import get_pool

logger = structlog.get_logger()


async def _main(event: dict[str, object], context: object) -> dict[str, object]:
    configure_logging()
    trace_id = str(uuid.uuid4())
    bind_trace_id(trace_id)

    pool = await get_pool()
    items = await pool.fetch("SELECT id FROM items WHERE attempt_count >= 50")
    calibrated = 0

    for item in items:
        item_id = item["id"]
        rows = await pool.fetch(
            """
            SELECT m.p_known AS theta, a.is_correct
            FROM attempts a
            JOIN student_skill_mastery m
              ON m.student_id = a.student_id
             AND m.skill_id = (SELECT skill_id FROM items WHERE id = a.item_id)
            WHERE a.item_id = $1
              AND a.created_at > NOW() - INTERVAL '90 days'
            """,
            item_id,
        )

        observations = [(2.0 * float(r["theta"]) - 1.0, bool(r["is_correct"])) for r in rows]
        params = fit_2pl(item_id=str(item_id), attempts=observations)

        await pool.execute(
            "UPDATE items SET irt_a=$1, irt_b=$2, irt_calibrated_at=NOW() WHERE id=$3",
            params.a,
            params.b,
            item_id,
        )
        calibrated += 1
        logger.info("irt_calibrated", item_id=item_id, a=params.a, b=params.b)

    return {"calibrated_items": calibrated}


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    return asyncio.run(_main(event, context))
