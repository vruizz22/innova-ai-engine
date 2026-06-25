from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class GenerationMode(StrEnum):
    """How A7 treats a question, based on what the PDF extraction carried (ADR v9 A7.1)."""

    VALIDATE = "VALIDATE"  # provided_solution_latex exists -> normalize + cross-check
    DERIVE = "DERIVE"  # only provided_answer -> derive and verify it reaches the answer
    # nothing in the PDF -> generate from scratch (always reviewable)
    FULL = "FULL"


class SolutionStep(BaseModel):
    """One canonical solution step (ADR-118)."""

    latex: str
    explanation_es: str
    # True when the step yields a verifiable intermediate result a student is
    # graded on.
    checkpoint: bool = False
    # Error codes a student is likely to make AT THIS STEP — constrained to the resolved
    # domain's ACTIVE catalog by the service before persisting (ADR v9 A7.2).
    expected_error_tags: list[str] = Field(default_factory=list)


class AltPath(BaseModel):
    """An alternative valid derivation (e.g. a different but correct method)."""

    label: str
    steps: list[SolutionStep] = Field(default_factory=list)


class TopicCandidate(BaseModel):
    """A classification candidate offered to the LLM. Since v9.1 these are derived
    from the error taxonomy (domain/subdomain) — always populated — instead of the
    sparse, hand-seeded `topics` table. `topic_id` links a curriculum topic only when
    one happens to map to the subdomain; the classification unit is the subdomain."""

    code: str
    name: str
    topic_id: str | None = None
    domain_id: str | None = None
    subdomain_id: str | None = None
    domain_code: str | None = None
    grade_level: int


class QuestionToSolve(BaseModel):
    """A guide question loaded from Postgres, ready for the generator."""

    question_id: str
    sequence: int
    label: str | None = None
    statement_latex: str
    provided_answer: str | None = None
    provided_solution_latex: str | None = None
    points: float = 1.0
    # max existing GuideSolution.version for this question (0 = none yet).
    current_version: int = 0


class GuideContext(BaseModel):
    """Everything A7 needs about a guide to generate its solutions."""

    guide_id: str
    course_id: str
    subject_id: str
    grade_level: int
    teacher_id: str
    title: str
    question_count: int
    questions: list[QuestionToSolve] = Field(default_factory=list)


class GeneratedSolution(BaseModel):
    """Sonnet `generate_solution` tool output for ONE question (ADR-118 + ADR-122)."""

    topic_code: str | None = None
    topic_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    final_answer: str
    steps: list[SolutionStep] = Field(default_factory=list)
    alt_paths: list[AltPath] = Field(default_factory=list)
    # Discrepancy note vs the PDF's own solution/answer (VALIDATE/DERIVE).
    validation_notes: str | None = None
    # VALIDATE/DERIVE: did the derivation reach the PDF's provided solution/answer?
    # None in FULL mode (nothing to match against).
    matches_provided: bool | None = None


class SolutionOutcome(BaseModel):
    """Per-question result, for logging."""

    question_id: str
    version: int
    status: str  # GuideQuestionStatus
    source: str  # SolutionSource
    topic_code: str | None = None
    needs_review: bool = False


class GuideSolveOutcome(BaseModel):
    """Worker-level summary for the handler response."""

    guide_id: str
    processed: int = 0
    needs_review_count: int = 0
    guide_status: str = "GENERATING_SOLUTIONS"
    alert_created: bool = False
