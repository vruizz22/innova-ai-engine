from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.guide_ingest.schemas import (
    ExtractGuideResult,
    FigureBBox,
    MergedQuestion,
    PrecheckResult,
)


@runtime_checkable
class PdfPrecheckPort(Protocol):
    """Cheap triage (Gemini 2.0 Flash) — kind/quality before Sonnet extraction."""

    async def precheck(self, pdf_bytes: bytes, *, trace_id: str = "") -> PrecheckResult: ...


@runtime_checkable
class GuideExtractorPort(Protocol):
    """Sonnet 4.6 extraction of one PDF chunk into structured questions."""

    async def extract_chunk(
        self,
        pdf_chunk: bytes,
        *,
        grade_level: int,
        page_count: int,
        trace_id: str = "") -> ExtractGuideResult: ...


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

    def publish(self, queue_url: str, body: str,
                *, trace_id: str = "") -> None: ...


@runtime_checkable
class GuideRepositoryPort(Protocol):
    """asyncpg writes against `guides` / `guide_questions` (CLAUDE.md §10)."""

    async def mark_extracting(self, guide_id: str) -> None: ...

    async def mark_failed(
        self,
        guide_id: str,
        *,
        source_kind: str,
        pages: int | None,
        reason: str) -> None: ...

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
