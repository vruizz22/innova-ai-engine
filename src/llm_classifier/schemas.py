from __future__ import annotations

from pydantic import BaseModel, Field


class Attempt(BaseModel):
    id: str
    # v9.1: after the taxonomy migration a guide question routes by domain_id +
    # subdomain_code; `topic` is only the (now optional) teacher-confirmed Topic
    # code, which is null for K-12 questions the teacher hasn't pinned to a Topic.
    # The backend sends `topic: null` for those, so accept None instead of raising.
    topic: str | None = None
    problem_statement: str
    canonical_solution: str
    raw_steps: list[object]
    final_answer: str
    student_id: str = ""
    # v8: backend sends the Domain UUID + subdomain code so the worker can route to
    # the right by-domain prompt/catalog. Optional to stay back-compatible
    # with v7.
    domain_id: str | None = None
    subdomain_code: str | None = None


class AttemptClassification(BaseModel):
    attempt_id: str
    error_type: str
    evidence: str
    confidence: float = Field(ge=0.0, le=1.0)


class ClassificationResult(BaseModel):
    classifications: list[AttemptClassification]
