from __future__ import annotations

import structlog


def bind_trace_id(trace_id: str) -> None:
    structlog.contextvars.bind_contextvars(trace_id=trace_id)


def clear_trace() -> None:
    structlog.contextvars.clear_contextvars()
