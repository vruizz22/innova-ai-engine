from __future__ import annotations

from typing import cast

import boto3  # type: ignore[import-untyped]
import structlog

from src.shared.settings import get_settings

logger = structlog.get_logger()


class PausedError(Exception):
    """Raised when an SSM cost-killswitch parameter reads 'true'."""


def is_paused(param_name: str) -> bool:
    """Read an SSM killswitch flag. Fails open (returns False) on any SSM error so a
    transient SSM outage never blocks the pipeline silently — the cost guard is a
    safety brake, not a correctness gate."""
    try:
        settings = get_settings()
        # type: ignore[misc]
        ssm = boto3.client("ssm", region_name=settings.app_aws_region)
        resp: dict[str, object] = ssm.get_parameter(Name=param_name)  # type: ignore[misc]
        param = cast(dict[str, object], resp["Parameter"])
        return str(param["Value"]).lower() == "true"
    except Exception:
        return False


def ensure_not_paused(param_name: str, *, trace_id: str = "") -> None:
    """Raise `PausedError` when the killswitch is active (call before each paid API call)."""
    if is_paused(param_name):
        logger.warning("killswitch_active", param=param_name, trace_id=trace_id)
        raise PausedError(f"paused by killswitch {param_name}")
