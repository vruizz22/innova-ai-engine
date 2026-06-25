"""Consumer local del pipeline async v9 — emula el event-source-mapping de SQS→Lambda.

En prod, AWS dispara cada worker cuando llega un mensaje a su cola. En local no hay ese
mapping, así que este script pollea las colas de LocalStack y despacha cada mensaje al
handler del worker correspondiente, con un evento con forma de SQS. Borra el mensaje solo
si el handler no reporta batchItemFailures (mismo contrato que prod).

Corre UN solo event loop y llama a `_main` (async) directamente — así el pool asyncpg
(cacheado en src.shared.postgres) vive en un único loop y se reutiliza entre mensajes
(llamar `handler`, que hace `asyncio.run` por mensaje, ataría el pool a un loop cerrado).

Uso (con LocalStack + Supabase + .env apuntando a :4566 y :54322, y crédito Anthropic):
    docker compose up -d localstack
    uv run python scripts/local_aws_bootstrap.py
    uv run python scripts/local_pipeline_consumer.py
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable

import boto3  # type: ignore[import-untyped]
import structlog
from dotenv import load_dotenv

load_dotenv()

from src.observability.logging import configure_logging  # noqa: E402
from src.pipeline import (  # noqa: E402
    adhoc_solver,
    exercise_generator,
    guide_ingest_worker,
    llm_consumer,
    solution_generator,
    submission_grader,
)

Handler = Callable[[dict[str, object], object], Awaitable[dict[str, object]]]

# LocalStack queues are created without a redrive policy, so a failing message would be
# redelivered forever — and each grading redelivery re-bills a vision call. Cap receives
# here to emulate prod's maxReceiveCount→DLQ: after this many attempts, drop the message.
MAX_RECEIVES = int(os.environ.get("LOCAL_MAX_RECEIVES", "3"))

# Cola de ENTRADA → handler que la procesa. (Los workers, al terminar, publican a la
# siguiente cola: ingest → solution-generation, grade → attempt-reprocess.)
# `llm-classify-queue` la alimenta el backend cuando el rule engine devuelve
# UNCLASSIFIED; el `llm_consumer` la clasifica y escribe el tag. Sin esto, en local
# los errores no determinísticos quedarían sin clasificar.
DISPATCH: dict[str, Handler] = {
    "guide-ingest-queue": guide_ingest_worker._main,
    "solution-generation-queue": solution_generator._main,
    "submission-grade-queue": submission_grader._main,
    "llm-classify-queue": llm_consumer._main,
    "adhoc-solve-queue": adhoc_solver._main,       # A10: scan ad-hoc sin guía
    "exercise-generate-queue": exercise_generator._main,  # B1: generación IA
}

logger = structlog.get_logger()


async def _poll_once(sqs: object, queue_url: str, handler: Handler) -> None:
    resp = sqs.receive_message(  # type: ignore[attr-defined]
        QueueUrl=queue_url,
        MaxNumberOfMessages=5,
        WaitTimeSeconds=2,
        AttributeNames=["ApproximateReceiveCount"],
        MessageAttributeNames=["All"],
    )
    for msg in resp.get("Messages", []):
        receive_count = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
        event: dict[str, object] = {
            "Records": [
                {
                    "messageId": msg["MessageId"],
                    "body": msg["Body"],
                    "receiptHandle": msg["ReceiptHandle"],
                    # Same shape as a real SQS→Lambda record, so a handler could honour it.
                    "attributes": {"ApproximateReceiveCount": str(receive_count)},
                }
            ]
        }
        try:
            outcome = await handler(event, None)
        except Exception as exc:  # noqa: BLE001 — un mensaje no debe tumbar el loop
            logger.error("dispatch_error", queue=queue_url, error=str(exc))
            outcome = {"batchItemFailures": [{"itemIdentifier": msg["MessageId"]}]}

        failures = outcome.get("batchItemFailures") or []
        if failures:
            if receive_count >= MAX_RECEIVES:
                # Exhausted retries → drop it (prod would move it to the DLQ). Stops the
                # redelivery loop so a poison message never keeps re-billing the LLM.
                sqs.delete_message(  # type: ignore[attr-defined]
                    QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"]
                )
                logger.error(
                    "dropped_after_max_receives",
                    queue=queue_url,
                    id=msg["MessageId"],
                    receives=receive_count,
                )
            else:
                logger.warning(
                    "left_on_queue",
                    queue=queue_url,
                    id=msg["MessageId"],
                    receives=receive_count,
                )
            continue
        sqs.delete_message(  # type: ignore[attr-defined]
            QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"]
        )
        logger.info("processed", queue=queue_url, id=msg["MessageId"])


async def main() -> None:
    configure_logging()
    region = os.environ.get("AWS_REGION", "us-east-1")
    sqs = boto3.client("sqs", region_name=region)  # type: ignore[misc]
    urls = {
        name: sqs.get_queue_url(QueueName=name)["QueueUrl"]  # type: ignore[misc]
        for name in DISPATCH
    }
    logger.info("consumer_started", queues=list(urls.keys()))
    while True:
        for name, handler in DISPATCH.items():
            await _poll_once(sqs, urls[name], handler)


if __name__ == "__main__":
    asyncio.run(main())
