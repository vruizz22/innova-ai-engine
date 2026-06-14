from __future__ import annotations

from pydantic import BaseModel, Field


class GradingEvalCase(BaseModel):
    """One labeled grading case: the golden verdict for a (submission) next to what the
    pipeline produced, plus cost/latency. Produced by replaying a golden set against a
    `prompt_version` (Victor's manual step, §0); this module only scores the records."""

    case_id: str
    prompt_version: str = ""
    # golden labels (human-curated truth)
    gold_is_correct: bool
    gold_score: float = Field(ge=0.0, le=1.0)
    gold_first_error_checkpoint: int | None = None
    # pipeline prediction
    pred_is_correct: bool
    pred_score: float = Field(ge=0.0, le=1.0)
    pred_first_error_checkpoint: int | None = None
    # operational outcomes (excluded from accuracy, reported as rates)
    illegible: bool = False
    unaligned: bool = False
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class GradingEvalReport(BaseModel):
    """Aggregate gate report for one prompt version (PLAN_v9_ADDENDUM §A9.1)."""

    prompt_version: str
    n_cases: int
    n_scored: int  # legible cases that count toward accuracy
    is_correct_accuracy: float
    score_mae: float
    checkpoint_accuracy: float
    illegible_rate: float
    unaligned_rate: float
    total_cost_usd: float
    avg_cost_usd: float
    p50_latency_ms: float
    p95_latency_ms: float
