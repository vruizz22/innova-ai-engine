from __future__ import annotations

import asyncio
import uuid

import structlog

from src.bkt.calibrate import calibrate_skill
from src.bkt.schemas import AttemptObservation
from src.observability.logging import configure_logging
from src.observability.tracing import bind_trace_id
from src.shared.postgres import get_pool

logger = structlog.get_logger()


async def _main(event: dict[str, object],
                context: object) -> dict[str, object]:
    configure_logging()
    trace_id = str(uuid.uuid4())
    bind_trace_id(trace_id)

    pool = await get_pool()
    skills = await pool.fetch("SELECT id FROM skills WHERE active = true")
    results: dict[str, object] = {}

    for skill in skills:
        skill_id = skill["id"]
        rows = await pool.fetch(
            """
            SELECT a.student_id, a.is_correct,
                   EXTRACT(EPOCH FROM a.created_at) AS ts
            FROM attempts a
            JOIN items i ON i.id = a.item_id
            WHERE i.skill_id = $1
              AND a.created_at > NOW() - INTERVAL '30 days'
            ORDER BY a.created_at
            """,
            skill_id,
        )

        if len(rows) < 50:
            logger.info("bkt_skip_low_data", skill_id=skill_id, n=len(rows))
            continue

        attempts = [
            AttemptObservation(
                student_id=str(r["student_id"]),
                skill_id=str(skill_id),
                is_correct=bool(r["is_correct"]),
                timestamp=float(r["ts"]),
            )
            for r in rows
        ]

        params = calibrate_skill(attempts)
        await pool.execute(
            """
            INSERT INTO skill_bkt_params
              (skill_id, p_l0, p_transit, p_slip, p_guess, log_likelihood, calibrated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (skill_id) DO UPDATE SET
              p_l0=$2, p_transit=$3, p_slip=$4, p_guess=$5,
              log_likelihood=$6, calibrated_at=NOW()
            """,
            skill_id,
            params.p_l0,
            params.p_transit,
            params.p_slip,
            params.p_guess,
            params.log_likelihood,
        )
        results[str(skill_id)] = params.model_dump()
        logger.info("bkt_calibrated", skill_id=skill_id, **params.model_dump())

    return {"calibrated_skills": results, "count": len(results)}


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    return asyncio.run(_main(event, context))
