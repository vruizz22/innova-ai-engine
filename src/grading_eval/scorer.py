from __future__ import annotations

from src.grading_eval.schemas import GradingEvalCase, GradingEvalReport


def load_cases(jsonl_text: str, *, prompt_version: str = "") -> list[GradingEvalCase]:
    """Parse JSONL (one case per line) into cases, optionally filtering to one
    prompt_version. Pure (text in, cases out) so the CLI's file read stays a thin shell
    and the parsing is unit-testable."""
    cases: list[GradingEvalCase] = []
    for line in jsonl_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        case = GradingEvalCase.model_validate_json(stripped)
        if prompt_version and case.prompt_version != prompt_version:
            continue
        cases.append(case)
    return cases


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: list[float], q: float) -> float:
    """Linear-interpolation percentile (q in [0,1]); 0.0 for an empty sample."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = q * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def score_grading(cases: list[GradingEvalCase], *, prompt_version: str = "") -> GradingEvalReport:
    """Aggregate accuracy/cost/latency over grading eval cases. Illegible cases are
    excluded from accuracy (they have no verdict to score) and surfaced as a rate; the
    checkpoint metric only counts legible cases that carry a golden checkpoint.

    Pure: no I/O, so it is unit-testable with synthetic cases (the CLI handles files)."""
    n_cases = len(cases)
    scored = [c for c in cases if not c.illegible]
    checkpoint_cases = [c for c in scored if c.gold_first_error_checkpoint is not None]

    is_correct_hits = [1.0 if c.gold_is_correct == c.pred_is_correct else 0.0 for c in scored]
    score_errors = [abs(c.gold_score - c.pred_score) for c in scored]
    checkpoint_hits = [
        1.0 if c.gold_first_error_checkpoint == c.pred_first_error_checkpoint else 0.0
        for c in checkpoint_cases
    ]
    latencies = [c.latency_ms for c in cases]
    total_cost = sum(c.cost_usd for c in cases)

    return GradingEvalReport(
        prompt_version=prompt_version,
        n_cases=n_cases,
        n_scored=len(scored),
        is_correct_accuracy=round(_mean(is_correct_hits), 4),
        score_mae=round(_mean(score_errors), 4),
        checkpoint_accuracy=round(_mean(checkpoint_hits), 4),
        illegible_rate=round(_mean([1.0 if c.illegible else 0.0 for c in cases]), 4),
        unaligned_rate=round(_mean([1.0 if c.unaligned else 0.0 for c in scored]), 4),
        total_cost_usd=round(total_cost, 6),
        avg_cost_usd=round(total_cost / n_cases, 6) if n_cases else 0.0,
        p50_latency_ms=round(_percentile(latencies, 0.5), 2),
        p95_latency_ms=round(_percentile(latencies, 0.95), 2),
    )
