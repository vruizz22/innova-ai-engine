from __future__ import annotations

import json

from src.observability.logging import configure_logging

configure_logging()


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"status": "ok", "service": "innova-ai-engine"}),
    }
