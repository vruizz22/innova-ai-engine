from __future__ import annotations

import boto3  # type: ignore[import-untyped]

from src.shared.settings import get_settings


class SqsPublisher:
    """`MessagePublisherPort` via SQS `send_message`, propagating `trace_id` as a
    message attribute (consumed by the next worker, CLAUDE.md §8)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = boto3.client(
            "sqs", region_name=settings.app_aws_region)  # type: ignore[misc]

    def publish(
            self,
            queue_url: str,
            body: str,
            *,
            trace_id: str = "") -> None:
        self._client.send_message(  # type: ignore[misc]
            QueueUrl=queue_url,
            MessageBody=body,
            MessageAttributes={
                "trace_id": {"DataType": "String", "StringValue": trace_id or "none"}
            },
        )
