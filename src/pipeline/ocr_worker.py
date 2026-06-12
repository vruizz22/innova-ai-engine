from __future__ import annotations

import asyncio
import uuid

import boto3  # type: ignore[import-untyped]
import structlog

from src.observability.logging import configure_logging
from src.observability.tracing import bind_trace_id
from src.ocr.image_utils import strip_exif_and_validate
from src.ocr.orchestrator import OcrOrchestrator
from src.shared.settings import get_settings

logger = structlog.get_logger()


async def _main(event: dict[str, object], context: object) -> dict[str, object]:
    configure_logging()
    trace_id = str(uuid.uuid4())
    bind_trace_id(trace_id)

    raw_records = event.get("Records", [])
    records: list[dict[str, object]] = list(raw_records) if isinstance(raw_records, list) else []
    if not records:
        return {"processed": 0}

    settings = get_settings()
    s3_client = boto3.client("s3", region_name=settings.app_aws_region)
    orchestrator = OcrOrchestrator()
    processed = 0

    for record in records:
        s3_info = record.get("s3", {})
        if not isinstance(s3_info, dict):
            continue
        bucket = s3_info.get("bucket", {})
        obj = s3_info.get("object", {})
        if not isinstance(bucket, dict) or not isinstance(obj, dict):
            continue
        bucket_name = str(bucket.get("name", ""))
        key = str(obj.get("key", ""))

        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        image_bytes: bytes = strip_exif_and_validate(response["Body"].read())

        result = await orchestrator.extract(image_bytes, trace_id=trace_id)
        logger.info(
            "ocr_complete",
            key=key,
            provider=result.provider,
            confidence=result.overall_confidence,
            steps=len(result.latex_steps),
            trace_id=trace_id,
        )
        processed += 1

    return {"processed": processed}


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    return asyncio.run(_main(event, context))
