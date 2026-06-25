from __future__ import annotations

from src.grading_eval.schemas import GradingEvalCase
from src.grading_eval.scorer import load_cases, score_grading


def _case(**over: object) -> GradingEvalCase:
    base: dict[str, object] = {
        "case_id": "c1",
        "prompt_version": "3.0",
        "gold_is_correct": True,
        "gold_score": 1.0,
        "gold_first_error_checkpoint": None,
        "pred_is_correct": True,
        "pred_score": 1.0,
        "pred_first_error_checkpoint": None,
        "illegible": False,
        "unaligned": False,
        "cost_usd": 0.0,
        "latency_ms": 0.0,
    }
    base.update(over)
    return GradingEvalCase.model_validate(base)


def test_perfect_predictions_score_one() -> None:
    cases = [
        _case(case_id="a", gold_first_error_checkpoint=2, pred_first_error_checkpoint=2),
        _case(
            case_id="b",
            gold_is_correct=False,
            gold_score=0.0,
            pred_is_correct=False,
            pred_score=0.0,
        ),
    ]
    report = score_grading(cases, prompt_version="3.0")

    assert report.n_cases == 2
    assert report.n_scored == 2
    assert report.is_correct_accuracy == 1.0
    assert report.score_mae == 0.0
    assert report.checkpoint_accuracy == 1.0
    assert report.illegible_rate == 0.0
    assert report.unaligned_rate == 0.0


def test_mixed_accuracy_and_mae() -> None:
    cases = [
        _case(
            case_id="a", gold_is_correct=True, gold_score=1.0, pred_is_correct=True, pred_score=0.8
        ),
        _case(
            case_id="b", gold_is_correct=True, gold_score=1.0, pred_is_correct=False, pred_score=0.0
        ),
    ]
    report = score_grading(cases)

    assert report.is_correct_accuracy == 0.5
    # |1.0-0.8| + |1.0-0.0| = 0.2 + 1.0 over 2 cases = 0.6
    assert report.score_mae == 0.6


def test_illegible_excluded_from_accuracy() -> None:
    cases = [
        _case(case_id="a"),
        _case(case_id="b", illegible=True, gold_is_correct=True, pred_is_correct=False),
    ]
    report = score_grading(cases)

    assert report.n_cases == 2
    assert report.n_scored == 1  # illegible case dropped from accuracy
    assert report.is_correct_accuracy == 1.0  # only the legible (correct) case counts
    assert report.illegible_rate == 0.5


def test_checkpoint_accuracy_only_over_gold_checkpoints() -> None:
    cases = [
        # has gold checkpoint, prediction matches -> hit
        _case(case_id="a", gold_first_error_checkpoint=1, pred_first_error_checkpoint=1),
        # has gold checkpoint, prediction differs -> miss
        _case(case_id="b", gold_first_error_checkpoint=2, pred_first_error_checkpoint=3),
        # no gold checkpoint -> not counted toward checkpoint accuracy
        _case(case_id="c", gold_first_error_checkpoint=None, pred_first_error_checkpoint=5),
    ]
    report = score_grading(cases)

    assert report.checkpoint_accuracy == 0.5


def test_unaligned_rate_over_scored_only() -> None:
    cases = [
        _case(case_id="a", unaligned=True),
        _case(case_id="b", unaligned=False),
        # illegible is not "scored", so it must not dilute the unaligned denominator
        _case(case_id="c", illegible=True, unaligned=True),
    ]
    report = score_grading(cases)

    assert report.n_scored == 2
    # 1 unaligned of 2 scored
    assert report.unaligned_rate == 0.5


def test_cost_and_latency_aggregation() -> None:
    cases = [
        _case(case_id="a", cost_usd=0.01, latency_ms=100.0),
        _case(case_id="b", cost_usd=0.02, latency_ms=200.0),
        _case(case_id="c", cost_usd=0.03, latency_ms=300.0),
    ]
    report = score_grading(cases)

    assert report.total_cost_usd == 0.06
    assert report.avg_cost_usd == 0.02
    assert report.p50_latency_ms == 200.0
    # p95 interpolates between 200 and 300: 200 + 0.9*100 = 290.0
    assert report.p95_latency_ms == 290.0


def test_empty_cases_are_all_zero() -> None:
    report = score_grading([], prompt_version="3.0")

    assert report.n_cases == 0
    assert report.n_scored == 0
    assert report.is_correct_accuracy == 0.0
    assert report.score_mae == 0.0
    assert report.avg_cost_usd == 0.0
    assert report.p50_latency_ms == 0.0


def test_load_cases_parses_and_filters_by_prompt_version() -> None:
    jsonl = "\n".join(
        [
            _case(case_id="a", prompt_version="3.0").model_dump_json(),
            "",  # blank lines are skipped
            _case(case_id="b", prompt_version="2.0").model_dump_json(),
            _case(case_id="c", prompt_version="3.0").model_dump_json(),
        ]
    )

    all_cases = load_cases(jsonl)
    assert [c.case_id for c in all_cases] == ["a", "b", "c"]

    only_v3 = load_cases(jsonl, prompt_version="3.0")
    assert [c.case_id for c in only_v3] == ["a", "c"]
