"""Re-enqueue unclassified guide-submission attempts into llm-classify-queue.

Guide submissions that were graded while the ai-engine consumer was offline land in
the DB with error_tag_id = NULL.  This script finds them, builds the same payload the
AttemptReprocessWorker sends, and publishes to llm-classify-queue so the running
consumer picks them up and classifies (or auto-creates catalog entries via the
suggest second-pass).

Usage:
    uv run python scripts/reclassify_unclassified.py [--dry-run]

Environment (from .env):
    DATABASE_URL          — local Postgres (e.g. postgresql://postgres:postgres@127.0.0.1:54322/postgres)
    SQS_LLM_CLASSIFY_URL  — local LocalStack queue URL
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from uuid import uuid4

import asyncpg
import boto3  # type: ignore[import-untyped]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# SQL: find PHOTO_GUIDE attempts with no error_tag_id, join all payload fields
# --------------------------------------------------------------------------
_QUERY = """
SELECT
    a.id                         AS attempt_id,
    a.student_id,
    gq.statement_latex           AS problem_statement,
    COALESCE(
        (SELECT gs_cur.final_answer
           FROM guide_solutions gs_cur
          WHERE gs_cur.guide_question_id = gq.id
            AND gs_cur.is_current = true
          ORDER BY gs_cur.version DESC
          LIMIT 1),
        ''
    )                            AS canonical_solution,
    t.code                       AS topic_code,
    COALESCE(t.domain_id::text, gq.domain_id::text)
                                 AS domain_id,
    COALESCE(sub_t.code, sub_gq.code)
                                 AS subdomain_code,
    COALESCE(
        (
            SELECT json_agg(
                json_build_object(
                    'expression', ast.content_latex,
                    'isFinal', (ast.step_index = max_step.max_idx)
                )
                ORDER BY ast.step_index
            )
            FROM attempt_steps ast
            CROSS JOIN (
                SELECT MAX(step_index) AS max_idx
                  FROM attempt_steps ast2
                 WHERE ast2.attempt_id = a.id
            ) max_step
            WHERE ast.attempt_id = a.id
        ),
        '[]'::json
    )                            AS raw_steps
FROM attempts a
JOIN guide_submissions gs  ON gs.attempt_id      = a.id
JOIN guide_questions    gq ON gs.guide_question_id = gq.id
LEFT JOIN topics     t      ON t.id     = gq.topic_id
LEFT JOIN subdomains sub_t  ON sub_t.id = t.subdomain_id
LEFT JOIN subdomains sub_gq ON sub_gq.id = gq.subdomain_id
WHERE a.is_correct   = false
  AND a.input_mode   = 'PHOTO_GUIDE'
  AND (
    -- attempt still pending with no tag
    a.error_tag_id IS NULL
    OR
    -- attempt was assigned the sentinel UNCLASSIFIED error_tag (seed bug)
    a.error_tag_id IN (
        SELECT id FROM error_tags
         WHERE code IN ('UNCLASSIFIED', 'TRANSVERSAL_LIKELY')
    )
  )
ORDER BY a.created_at
"""


def _build_payload(row: asyncpg.Record) -> dict[str, object]:
    raw_steps: list[object] = json.loads(row["raw_steps"]) if row["raw_steps"] else []
    final_answer = ""
    if raw_steps and isinstance(raw_steps[-1], dict):
        last: dict[str, object] = raw_steps[-1]  # type: ignore[assignment]
        final_answer = str(last.get("expression", ""))

    return {
        "id": str(row["attempt_id"]),
        "topic": row["topic_code"],
        "domain_id": row["domain_id"],
        "subdomain_code": row["subdomain_code"],
        "problem_statement": row["problem_statement"] or "",
        "canonical_solution": row["canonical_solution"] or "",
        "raw_steps": raw_steps,
        "final_answer": final_answer,
        "student_id": str(row["student_id"]),
    }


async def run(dry_run: bool) -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    sqs_url = os.environ.get(
        "SQS_LLM_CLASSIFY_URL",
        "http://localhost:4566/000000000000/llm-classify-queue",
    )

    if not database_url:
        raise RuntimeError("DATABASE_URL not set")

    log.info("Connecting to DB…")
    conn = await asyncpg.connect(database_url)
    try:
        rows = await conn.fetch(_QUERY)
    finally:
        await conn.close()

    if not rows:
        log.info("No unclassified PHOTO_GUIDE attempts found — nothing to do.")
        return

    log.info("Found %d unclassified attempts", len(rows))

    if dry_run:
        for row in rows:
            log.info("DRY-RUN attempt_id=%s student=%s", row["attempt_id"], row["student_id"])
        return

    sqs = boto3.client(
        "sqs",
        region_name=os.environ.get("APP_AWS_REGION", "us-east-1"),
        endpoint_url=os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
    )

    ok = 0
    fail = 0
    for row in rows:
        payload = _build_payload(row)
        attempt_id = str(row["attempt_id"])
        trace_id = str(uuid4())
        try:
            sqs.send_message(
                QueueUrl=sqs_url,
                MessageBody=json.dumps(payload, ensure_ascii=False),
                MessageAttributes={
                    "trace_id": {
                        "DataType": "String",
                        "StringValue": trace_id,
                    }
                },
            )
            log.info("Enqueued attempt_id=%s trace_id=%s", attempt_id, trace_id)
            ok += 1
        except Exception as exc:
            log.error("Failed to enqueue attempt_id=%s: %s", attempt_id, exc)
            fail += 1

    log.info("Done — enqueued=%d failed=%d", ok, fail)
    if ok:
        log.info(
            "The running consumer (local_pipeline_consumer.py) will process them via "
            "llm-classify-queue and auto-create catalog entries for unknown errors."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-enqueue unclassified guide attempts")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List attempts without enqueuing",
    )
    args = parser.parse_args()

    # Load .env from the repo root of innova-ai-engine so DATABASE_URL etc. are available
    env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    val = val.strip().strip('"').strip("'")
                    os.environ.setdefault(key.strip(), val)

    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
