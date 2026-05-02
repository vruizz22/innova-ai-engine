#!/usr/bin/env python3
from __future__ import annotations
import os
import subprocess

LAMBDAS = [
    "nightly-bkt",
    "nightly-irt",
    "llm-classifier",
    "ocr-worker",
]

AWS_ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "123456789012")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
ECR_BASE = f"{AWS_ACCOUNT_ID}.dkr.ecr.{AWS_REGION}.amazonaws.com"


def run(cmd: str) -> None:
    print(f"$ {cmd}")
    subprocess.run(cmd, shell=True, check=True)


def main() -> None:
    for name in LAMBDAS:
        image_uri = f"{ECR_BASE}/innova-{name}:latest"
        run(
            f"docker build --build-arg LAMBDA_NAME={name} -f Dockerfile.lambda -t {image_uri} .")
        run(f"docker push {image_uri}")
        run(
            f"aws lambda update-function-code "
            f"--function-name innova-{name} --image-uri {image_uri}"
        )
        print(f"Deployed innova-{name}")


if __name__ == "__main__":
    main()
