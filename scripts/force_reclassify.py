"""Force re-classification of specific PHOTO_GUIDE attempts by ID.

Use this when an attempt was already CLASSIFIED but with a wrong error tag
(e.g., TASK_SWITCHING_FAILURE when the actual error was a fraction addition error).
The script resets the attempt's status to PENDING and re-enqueues it to
llm-classify-queue so the consumer re-runs classification.

Usage:
    uv run python scripts/force_reclassify.py <attempt_id> [<attempt_id> ...]
    uv run python scripts/force_reclassify.py --all-wrong-tag TASK_SWITCHING_FAILURE_UNRELATED_WORK
    uv run python scripts/force_reclassify.py --dry-run <attempt_id>

Environment (from .env):
    DATABASE_URL          — local Postgres
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

_PAYLOAD_QUERY = """
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
    )                            AS raw_steps,
    et.code                      AS current_error_tag
FROM attempts a
JOIN guide_submissions gs  ON gs.attempt_id      = a.id
JOIN guide_questions    gq ON gs.guide_question_id = gq.id
LEFT JOIN topics     t      ON t.id     = gq.topic_id
LEFT JOIN subdomains sub_t  ON sub_t.id = t.subdomain_id
LEFT JOIN subdomains sub_gq ON sub_gq.id = gq.subdomain_id
LEFT JOIN error_tags et     ON et.id    = a.error_tag_id
WHERE a.input_mode = 'PHOTO_GUIDE'
  AND a.is_correct = false
  AND a.id::text = ANY($1)
ORDER BY a.created_at
"""

_BY_TAG_QUERY = """
SELECT a.id::text AS id
FROM attempts a
JOIN error_tags et ON et.id = a.error_tag_id
WHERE a.input_mode  = 'PHOTO_GUIDE'
  AND a.is_correct  = false
  AND et.code       = $1
"""

_RESET_SQL = """
UPDATE attempts
   SET status       = 'PENDING',
       error_tag_id = NULL,
       classified_at = NULL
 WHERE id::text = ANY($1)
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


async def run(
        attempt_ids: list[str],
        wrong_tag: str | None,
        dry_run: bool) -> None:
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
        if wrong_tag:
            tag_rows = await conn.fetch(_BY_TAG_QUERY, wrong_tag)
            extra_ids = [str(r["id"]) for r in tag_rows]
            if extra_ids:
                log.info("Found %d attempts with tag '%s'", len(extra_ids), wrong_tag)
                attempt_ids = list({*attempt_ids, *extra_ids})
            else:
                log.info("No attempts found with tag '%s'", wrong_tag)

        if not attempt_ids:
            log.info("No attempt IDs to process — nothing to do.")
            return

        rows = await conn.fetch(_PAYLOAD_QUERY, attempt_ids)
        found_ids = {str(r["attempt_id"]) for r in rows}
        missing = set(attempt_ids) - found_ids
        if missing:
            log.warning("Attempts not found (not PHOTO_GUIDE or wrong ID): %s", missing)

        if not rows:
            log.info("No processable attempts found.")
            return

        log.info("Will re-classify %d attempt(s):", len(rows))
        for row in rows:
            log.info(
                "  attempt_id=%s  current_tag=%s  problem=%.60s",
                row["attempt_id"],
                row["current_error_tag"],
                (row["problem_statement"] or "").replace("\n", " "),
            )

        if dry_run:
            log.info("DRY-RUN — no DB changes, no messages sent.")
            return

        # Reset to PENDING so the consumer can re-classify.
        await conn.execute(_RESET_SQL, attempt_ids)
        log.info("Reset %d attempt(s) to PENDING (error_tag_id = NULL).", len(rows))

    finally:
        await conn.close()

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
            "The running consumer (local_pipeline_consumer.py) will re-classify them."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Force re-classification of already-classified PHOTO_GUIDE attempts"
    )
    parser.add_argument(
        "attempt_ids",
        nargs="*",
        help="One or more attempt UUIDs to re-classify",
    )
    parser.add_argument(
        "--all-wrong-tag",
        metavar="TAG_CODE",
        help="Re-classify all PHOTO_GUIDE attempts currently assigned this error tag code",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without modifying DB or enqueuing",
    )
    args = parser.parse_args()

    env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    val = val.strip().strip('"').strip("'")
                    os.environ.setdefault(key.strip(), val)

    asyncio.run(run(args.attempt_ids, args.all_wrong_tag, args.dry_run))


if __name__ == "__main__":
    main()
