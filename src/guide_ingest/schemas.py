from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class PdfKind(StrEnum):
    """Result of the Gemini precheck — mirrors `Guide.source_kind` on the backend."""

    SCANNED = "SCANNED"
    DIGITAL = "DIGITAL"
    MIXED = "MIXED"


class PrecheckResult(BaseModel):
    """Cheap Gemini Flash triage before spending Sonnet tokens (ADR v9 A6.1)."""

    kind: PdfKind
    content_pages: list[int] = Field(default_factory=list)
    quality: float = Field(ge=0.0, le=1.0)
    notes: str | None = None


class FigureBBox(BaseModel):
    """Figure region on a page, in page-normalized [0,1] coordinates, top-left origin.

    The LLM sees a rendered page, so normalized top-left coords are the most stable
    contract; `Pypdfium2Processor.crop_figure` converts them to pixels. `page` is the
    absolute 0-based page index in the source PDF (chunk offsets resolved by the
    service before cropping)."""

    page: int = Field(ge=0)
    x0: float = Field(ge=0.0, le=1.0)
    y0: float = Field(ge=0.0, le=1.0)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)


class ExtractedQuestion(BaseModel):
    """One question as returned by the Sonnet `extract_guide` tool (ADR v9 A6.2)."""

    label: str | None = None
    statement_latex: str
    statement_text: str
    provided_answer: str | None = None
    provided_solution_latex: str | None = None
    figure_bboxes: list[FigureBBox] = Field(default_factory=list)
    # True when the chunk boundary split this question; merged into the previous chunk's
    # last question by `merge_chunks`.
    continues_previous: bool = False


class ExtractGuideResult(BaseModel):
    """Per-chunk extractor output."""

    questions: list[ExtractedQuestion] = Field(default_factory=list)


class MergedQuestion(BaseModel):
    """A question after chunk merge + sequence assignment, ready to persist. Figure keys
    are filled once the figures are cropped and uploaded to S3."""

    sequence: int = Field(ge=1)
    label: str | None = None
    statement_latex: str
    statement_text: str
    provided_answer: str | None = None
    provided_solution_latex: str | None = None
    figure_bboxes: list[FigureBBox] = Field(default_factory=list)
    figure_keys: list[str] = Field(default_factory=list)


class GuideIngestMessage(BaseModel):
    """Inbound SQS body: backend -> `guide-ingest-queue`.

    Mirrors `GuideIngestMessage` in backend `src/shared/sqs/guide-messages.ts`."""

    guide_id: str
    source_pdf_key: str
    course_grade_level: int
    trace_id: str = ""


class SolutionGenMessage(BaseModel):
    """Outbound SQS body: ai-engine -> `solution-generation-queue`.

    `guide_question_id = None` means "the whole guide" (A7 default)."""

    guide_id: str
    guide_question_id: str | None = None
    trace_id: str = ""


class IngestOutcome(BaseModel):
    """Worker-level summary for logging / handler response."""

    guide_id: str
    status: str
    question_count: int = 0
    failure_reason: str | None = None
