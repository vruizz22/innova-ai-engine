from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AlignVerdict(StrEnum):
    """Per-step verdict against the official solution (ADR v9 A8.1)."""

    OK = "OK"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class TranscriptionStep(BaseModel):
    """One transcribed student step."""

    idx: int
    latex: str
    legible: bool = True


class Transcription(BaseModel):
    """The student's handwritten work, transcribed by Haiku vision."""

    steps: list[TranscriptionStep] = Field(default_factory=list)
    final_answer: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class AlignMatch(BaseModel):
    """A student step mapped to a checkpoint of the official solution."""

    student_step_idx: int
    solution_checkpoint_idx: int | None = None
    verdict: AlignVerdict


class Alignment(BaseModel):
    """How the student's path lines up with the pauta. `path` is MAIN | ALT_<n> |
    UNALIGNED."""

    matches: list[AlignMatch] = Field(default_factory=list)
    path: str = "UNALIGNED"


class Provisional(BaseModel):
    """The grader's provisional verdict (refined downstream by the rule engine)."""

    is_correct: bool
    score_0_1: float = Field(ge=0.0, le=1.0)
    first_error_step_idx: int | None = None


class TranscribeAndAlign(BaseModel):
    """Haiku `transcribe_and_align` tool output for one submission (ADR v9 A8.1)."""

    transcription: Transcription
    alignment: Alignment
    provisional: Provisional


class GradeSubmissionMessage(BaseModel):
    """Inbound SQS body: backend -> `submission-grade-queue`. Minimal — the worker loads
    photos + the current pauta from Postgres."""

    guide_submission_id: str
    trace_id: str = ""


class SubmissionContext(BaseModel):
    """Everything A8 needs to grade one submission (loaded from Postgres + catalog)."""

    guide_submission_id: str
    guide_id: str
    guide_question_id: str
    student_id: str
    attempt_number: int
    photo_keys: list[str] = Field(default_factory=list)
    grade_level: int
    question_label: str | None = None
    solution_version: int
    solution_steps_json: str  # canonical ADR-118 document (raw JSON)
    solution_final_answer: str
    domain_id: str | None = None
    domain_catalog_text: str = ""  # catalog extract anchoring the cached block


class AlignmentSummary(BaseModel):
    """Compact alignment digest carried to the reprocess queue."""

    path: str
    first_error_checkpoint: int | None = None
    score_0_1: float = Field(ge=0.0, le=1.0)


class ReprocessMessage(BaseModel):
    """Outbound SQS body: ai-engine -> existing `attempt-reprocess-queue` (ADR v9 A8.1).

    `attempt_id=None` distinguishes a guide submission from a normal attempt."""

    attempt_id: None = None
    guide_submission_id: str
    guide_question_id: str
    latex_steps: list[str] = Field(default_factory=list)
    provider: str = "claude-haiku"
    confidence: float = Field(ge=0.0, le=1.0)
    alignment_summary: AlignmentSummary
    trace_id: str = ""


class GradeOutcome(BaseModel):
    """Worker-level summary for the handler response."""

    guide_submission_id: str
    status: str  # SubmissionStatus
    score: float | None = None
    is_correct: bool | None = None
    illegible: bool = False
    published: bool = False
    failure_reason: str | None = None
