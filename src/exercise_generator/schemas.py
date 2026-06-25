from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateExercisesMessage(BaseModel):
    """Inbound SQS body: backend → `exercise-generate-queue`."""

    subdomain_code: str
    grade_level: int = Field(ge=1, le=12)
    target_error_codes: list[str] = Field(min_length=1)
    count: int = Field(ge=1, le=10)
    trace_id: str = ""


class GeneratedExercise(BaseModel):
    """One exercise as returned by the Haiku `generate_exercises` tool."""

    problem_latex: str = Field(min_length=1)
    correct_answer_latex: str = Field(min_length=1)
    solution_steps_latex: list[str] = Field(default_factory=list)
    irt_a: float = Field(default=1.0, ge=0.5, le=3.0)
    irt_b: float = Field(default=0.0, ge=-3.0, le=3.0)
    target_error_codes: list[str] = Field(default_factory=list)


class GenerateExercisesTool(BaseModel):
    """Haiku `generate_exercises` tool output."""

    exercises: list[GeneratedExercise] = Field(default_factory=list)


class GenerateExercisesResult(BaseModel):
    """Worker-level outcome."""

    subdomain_code: str
    requested: int
    generated: int
    persisted: int
    failure_reason: str | None = None
