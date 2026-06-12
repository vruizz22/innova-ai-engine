from __future__ import annotations

from typing import cast

import boto3  # type: ignore[import-untyped]

from src.shared.settings import get_settings


class S3ObjectStore:
    """`ObjectStorePort` scoped to a single bucket (the guides bucket by default)."""

    def __init__(self, bucket: str | None = None) -> None:
        settings = get_settings()
        self._bucket = bucket if bucket is not None else settings.s3_guides_bucket
        self._client = boto3.client(
            "s3", region_name=settings.app_aws_region)  # type: ignore[misc]

    def get(self, key: str) -> bytes:
        resp = self._client.get_object(
            Bucket=self._bucket,
            Key=key)  # type: ignore[misc]
        return cast(bytes, resp["Body"].read())  # type: ignore[misc]

    def put(self, key: str, body: bytes, *, content_type: str) -> None:
        self._client.put_object(  # type: ignore[misc]
            Bucket=self._bucket, Key=key, Body=body, ContentType=content_type
        )
