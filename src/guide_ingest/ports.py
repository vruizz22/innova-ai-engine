from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.guide_ingest.schemas import (
    ExtractGuideResult,
    FigureBBox,
    MergedQuestion,
    PrecheckResult,
)
from src.observability.cost import TokenUsage


@runtime_checkable
class PdfPrecheckPort(Protocol):
    """Cheap triage (Gemini Flash) — kind/quality before Sonnet extraction."""

    async def precheck(self, pdf_bytes: bytes, *, trace_id: str = "") -> PrecheckResult: ...


@runtime_checkable
class GuideExtractorPort(Protocol):
    """Sonnet 4.6 extraction of one PDF chunk into structured questions, plus the call's
    token usage so the service can accumulate the per-guide cost (A9.4)."""

    async def extract_chunk(
        self, pdf_chunk: bytes, *, grade_level: int, page_count: int, trace_id: str = ""
    ) -> tuple[ExtractGuideResult, TokenUsage]: ...


@runtime_checkable
class PdfProcessorPort(Protocol):
    """CPU-bound PDF operations (pypdfium2). Sync is fine — not DB/HTTP (CLAUDE.md §10/§13)."""

    def page_count(self, pdf_bytes: bytes) -> int: ...

    def slice_pages(self, pdf_bytes: bytes, start: int, end: int) -> bytes:
        """Return a new PDF with pages [start, end) (0-based, end exclusive)."""
        ...

    def crop_figure(self, pdf_bytes: bytes, bbox: FigureBBox) -> bytes:
        """Render the bbox region of `bbox.page` and return PNG bytes."""
        ...


@runtime_checkable
class ObjectStorePort(Protocol):
    """S3 object access scoped to a single bucket (set on the adapter)."""

    def get(self, key: str) -> bytes: ...

    def put(self, key: str, body: bytes, *, content_type: str) -> None: ...


@runtime_checkable
class MessagePublisherPort(Protocol):
    """SQS producer."""

    def publish(self, queue_url: str, body: str, *, trace_id: str = "") -> None: ...


@runtime_checkable
class GuideRepositoryPort(Protocol):
    """asyncpg writes against `guides` / `guide_questions` (CLAUDE.md §10)."""

    async def mark_extracting(self, guide_id: str) -> None: ...

    async def mark_failed(
        self, guide_id: str, *, source_kind: str, pages: int | None, reason: str
    ) -> None: ...

    async def complete(
        self,
        guide_id: str,
        questions: list[MergedQuestion],
        *,
        source_kind: str,
        pages: int | None,
        latex_key: str,
        extraction_confidence: float,
        extraction_model: str,
    ) -> None: ...

    async def save_cost_event(
        self,
        *,
        worker: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_input_tokens: int,
        cache_read_input_tokens: int,
        cost_usd: float,
        trace_id: str,
    ) -> None:
        """Persist one LLM cost event for the admin cost dashboard (A9.4/C2).
        Must swallow errors — cost events must never block the ingest flow."""
        ...
