from __future__ import annotations

from pydantic import BaseModel, Field


class Attempt(BaseModel):
    id: str
    topic: str
    problem_statement: str
    canonical_solution: str
    raw_steps: list[object]
    final_answer: str
    student_id: str = ""


class AttemptClassification(BaseModel):
    attempt_id: str
    error_type: str
    evidence: str
    confidence: float = Field(ge=0.0, le=1.0)


class ClassificationResult(BaseModel):
    classifications: list[AttemptClassification]
