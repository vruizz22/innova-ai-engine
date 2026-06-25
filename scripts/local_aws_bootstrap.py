"""Crea las colas SQS y los buckets S3 del pipeline v9 en LocalStack (:4566).

Idempotente. Lee la config del .env (AWS_ENDPOINT_URL + creds dummy) vía load_dotenv,
de modo que boto3 apunte a LocalStack en vez de AWS real.

Uso:
    docker compose up -d localstack      # en innova-backend-serverless
    uv run python scripts/local_aws_bootstrap.py
"""

from __future__ import annotations

import os

import boto3  # type: ignore[import-untyped]
from dotenv import load_dotenv

load_dotenv()

# Colas que consume/publica el pipeline (nombres = los de los .env del back y ai-engine).
QUEUES = [
    "guide-ingest-queue",
    "solution-generation-queue",
    "submission-grade-queue",
    "attempt-reprocess-queue",
    "llm-classify-queue",
    "ocr-queue",
    "adhoc-solve-queue",           # A10: scan sin guía, álgebra simbólica
    "exercise-generate-queue",     # B1: generación IA de ejercicios por subdomain
]

BUCKETS = ["innova-guides-dev", "innova-submissions-dev"]


def main() -> None:
    region = os.environ.get("AWS_REGION", "us-east-1")
    endpoint = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
    print(f"🔧 Bootstrapping LocalStack en {endpoint} (region {region})")

    sqs = boto3.client("sqs", region_name=region)
    for name in QUEUES:
        url = sqs.create_queue(QueueName=name)["QueueUrl"]
        print(f"  ✅ queue  {name:28} {url}")

    s3 = boto3.client("s3", region_name=region)
    # CORS so the web app (localhost:3005) can PUT directly to the presigned URL
    # and poll figures via presigned GET. Required for the browser upload to work.
    cors = {
        "CORSRules": [
            {
                "AllowedHeaders": ["*"],
                "AllowedMethods": ["GET", "PUT", "HEAD"],
                "AllowedOrigins": [
                    "http://localhost:3005",
                    "http://127.0.0.1:3005",
                ],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3000,
            }
        ]
    }
    for bucket in BUCKETS:
        try:
            s3.create_bucket(Bucket=bucket)
            print(f"  ✅ bucket {bucket}")
        except Exception as exc:  # noqa: BLE001 — idempotente: ya existe / etc.
            print(f"  •  bucket {bucket} (ya existe o: {exc})")
        try:
            s3.put_bucket_cors(Bucket=bucket, CORSConfiguration=cors)
            print(f"     ↳ CORS aplicado a {bucket}")
        except Exception as exc:  # noqa: BLE001
            print(f"     ↳ CORS no aplicado a {bucket}: {exc}")

    print("🎉 LocalStack listo.")


if __name__ == "__main__":
    main()
