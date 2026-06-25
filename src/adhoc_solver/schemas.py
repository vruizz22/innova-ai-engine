from __future__ import annotations

from pydantic import BaseModel, Field


class AdhocSolveMessage(BaseModel):
    """SQS message sent by the backend when a student scans an exercise ad-hoc
    (no guide context). Carries the OCR-extracted problem + the student's work."""

    attempt_id: str
    problem_latex: str
    student_steps: list[str] = Field(default_factory=list)
    student_final_answer: str
    student_id: str = ""
    # grade_level used to narrow taxonomy candidates (default 7 = 7th grade)
    grade_level: int = 7
    trace_id: str = ""


class AdhocSolveOutcome(BaseModel):
    """Worker-level summary returned to the Lambda handler."""

    attempt_id: str
    is_correct: bool | None = None
    derived_answer: str = ""
    error_tag_code: str | None = None
    status: str = "CLASSIFIED"
    failure_reason: str | None = None
