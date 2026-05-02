from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BktParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    p_l0: float = Field(..., ge=0.0, le=1.0, description="Prior P(knows skill)")
    p_transit: float = Field(..., ge=0.0, le=1.0, description="P(learns per opportunity)")
    p_slip: float = Field(..., ge=0.0, le=0.5, description="P(fails when knows)")
    p_guess: float = Field(..., ge=0.0, le=0.5, description="P(correct when doesn't know)")
    log_likelihood: float | None = None

    @model_validator(mode="after")
    def check_identifiability(self) -> BktParams:
        if self.p_slip + self.p_guess >= 1.0:
            raise ValueError("p_slip + p_guess must be < 1.0 for identifiability")
        return self


class AttemptObservation(BaseModel):
    student_id: str
    skill_id: str
    is_correct: bool
    timestamp: float
