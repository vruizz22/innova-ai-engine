from __future__ import annotations

import os
import time
from collections.abc import Mapping, Sequence

import structlog

logger = structlog.get_logger()

EMF_NAMESPACE = "Innova/Guides"

# EMF metric units (CloudWatch vocabulary). Rates/ratios use None (dimensionless 0..1)
# so the dashboard reads them raw; counts use Count; money uses None (USD).
UNIT_NONE = "None"
UNIT_COUNT = "Count"
UNIT_MS = "Milliseconds"

# A9.4 metric names (PLAN_v9_ADDENDUM §A9.4). Underscore form (valid kwargs); the dotted
# prefixes from the plan are implied by EMF_NAMESPACE.
M_INGEST_COST_USD = "ingest_cost_usd"
M_EXTRACTION_FAILED = "extraction_failed_count"
M_NEEDS_REVIEW_RATIO = "needs_review_ratio"
M_COST_PER_SUBMISSION = "cost_per_submission"
M_CACHE_HIT_RATE = "cache_hit_rate"
M_UNALIGNED_RATE = "unaligned_rate"
M_ILLEGIBLE_RATE = "illegible_rate"


def _now_ms() -> int:
    return int(time.time() * 1000)


def build_emf(
    *,
    namespace: str,
    metrics: Sequence[tuple[str, float, str]],
    dimensions: Mapping[str, str],
    fields: Mapping[str, object] | None,
    timestamp_ms: int,
) -> dict[str, object]:
    """Build a CloudWatch Embedded Metric Format record. Logging this dict as top-level
    JSON to stdout lets CloudWatch auto-extract the metrics — no PutMetricData call, IAM
    grant, or sync HTTP needed (A9.4). `metrics` are (name, value, unit) tuples,
    `dimensions` become one dimension set, `fields` are extra non-metric context."""
    metric_defs: list[dict[str, str]] = [
        {"Name": name, "Unit": unit} for name, _value, unit in metrics
    ]
    record: dict[str, object] = {
        "_aws": {
            "Timestamp": timestamp_ms,
            "CloudWatchMetrics": [
                {
                    "Namespace": namespace,
                    "Dimensions": [list(dimensions.keys())],
                    "Metrics": metric_defs,
                }
            ],
        },
    }
    for key, dim_value in dimensions.items():
        record[key] = dim_value
    for name, value, _unit in metrics:
        record[name] = value
    if fields:
        for key, field_value in fields.items():
            record[key] = field_value
    return record


def emit_metrics(
    metrics: Sequence[tuple[str, float, str]],
    *,
    namespace: str = EMF_NAMESPACE,
    dimensions: Mapping[str, str] | None = None,
    **fields: object,
) -> None:
    """Emit one EMF metric record to stdout via structlog (CLAUDE.md §9). Defaults the
    dimension set to the deploy Stage so per-environment dashboards stay separated."""
    dims = dict(dimensions) if dimensions else {"Stage": os.getenv("STAGE", "dev")}
    record = build_emf(
        namespace=namespace,
        metrics=metrics,
        dimensions=dims,
        fields=fields,
        timestamp_ms=_now_ms(),
    )
    logger.info("emf_metric", **record)
