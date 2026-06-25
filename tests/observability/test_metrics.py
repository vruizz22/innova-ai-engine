from __future__ import annotations

from typing import cast

import pytest

import src.observability.metrics as metrics_mod
from src.observability.metrics import (
    EMF_NAMESPACE,
    UNIT_COUNT,
    UNIT_NONE,
    build_emf,
    emit_metrics,
)


def test_build_emf_structure_and_top_level_values() -> None:
    record = build_emf(
        namespace="Innova/Guides",
        metrics=[("needs_review_ratio", 0.25, UNIT_NONE)],
        dimensions={"Stage": "prod"},
        fields={"guide_id": "g1"},
        timestamp_ms=1234,
    )

    aws = cast(dict[str, object], record["_aws"])
    assert aws["Timestamp"] == 1234
    cw = cast(list[dict[str, object]], aws["CloudWatchMetrics"])[0]
    assert cw["Namespace"] == "Innova/Guides"
    assert cw["Dimensions"] == [["Stage"]]
    assert cw["Metrics"] == [{"Name": "needs_review_ratio", "Unit": "None"}]
    # dimension, metric value and field all surface as top-level keys for EMF extraction.
    assert record["Stage"] == "prod"
    assert record["needs_review_ratio"] == 0.25
    assert record["guide_id"] == "g1"


def test_build_emf_supports_multiple_metrics() -> None:
    record = build_emf(
        namespace=EMF_NAMESPACE,
        metrics=[
            ("illegible_rate", 1.0, UNIT_NONE),
            ("unaligned_rate", 0.0, UNIT_NONE),
        ],
        dimensions={"Stage": "dev"},
        fields=None,
        timestamp_ms=1,
    )
    aws = cast(dict[str, object], record["_aws"])
    cw = cast(list[dict[str, object]], aws["CloudWatchMetrics"])[0]
    names = [m["Name"] for m in cast(list[dict[str, object]], cw["Metrics"])]
    assert names == ["illegible_rate", "unaligned_rate"]
    assert record["illegible_rate"] == 1.0
    assert record["unaligned_rate"] == 0.0


def test_emit_metrics_defaults_stage_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Every record key must be a valid identifier so **record unpacks into structlog.
    captured: dict[str, object] = {}

    def _fake_info(event: str, **kw: object) -> None:
        captured["event"] = event
        captured.update(kw)

    monkeypatch.setenv("STAGE", "staging")
    monkeypatch.setattr(metrics_mod.logger, "info", _fake_info)

    emit_metrics([("extraction_failed_count", 1.0, UNIT_COUNT)], trace_id="tr1")

    assert captured["event"] == "emf_metric"
    assert captured["Stage"] == "staging"
    assert captured["extraction_failed_count"] == 1.0
    assert captured["trace_id"] == "tr1"
    assert "_aws" in captured
