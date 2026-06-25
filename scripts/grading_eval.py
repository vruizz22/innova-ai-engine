#!/usr/bin/env python3
"""Grading-eval gate (PLAN_v9_ADDENDUM §A9.1).

Scores a recorded grading run (golden labels vs pipeline predictions, one JSONL
case per line) and prints an aggregate report. Exit code gates CI:
  0 -> accuracy/MAE within thresholds
  1 -> thresholds breached
  2 -> no cases for the requested prompt_version

The live pipeline run that produces predictions is a separate (manual) step; this
script only consumes the resulting JSONL so it stays fast and side-effect free.

Usage:
  uv run python scripts/grading_eval.py --input runs/grading_v3.jsonl \
      --prompt-version 3.0 --min-accuracy 0.85 --max-mae 0.15
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.grading_eval.scorer import load_cases, score_grading

_MIN_IS_CORRECT_ACCURACY = 0.85
_MAX_SCORE_MAE = 0.15


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score a grading eval run.")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="JSONL file of grading cases.")
    parser.add_argument(
        "--prompt-version",
        default="",
        help="Only score cases tagged with this prompt_version (default: all).",
    )
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=_MIN_IS_CORRECT_ACCURACY,
        help="Minimum is_correct accuracy to pass the gate.",
    )
    parser.add_argument(
        "--max-mae",
        type=float,
        default=_MAX_SCORE_MAE,
        help="Maximum score MAE to pass the gate.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    cases = load_cases(
        args.input.read_text(
            encoding="utf-8"),
        prompt_version=args.prompt_version)
    if not cases:
        sys.stderr.write("no grading cases for the requested prompt_version\n")
        return 2

    report = score_grading(cases, prompt_version=args.prompt_version)
    sys.stdout.write(json.dumps(report.model_dump(), indent=2) + "\n")

    passed = report.is_correct_accuracy >= args.min_accuracy and report.score_mae <= args.max_mae
    if not passed:
        sys.stderr.write(
            f"GATE FAILED: accuracy={report.is_correct_accuracy} "
            f"(min {args.min_accuracy}), mae={report.score_mae} "
            f"(max {args.max_mae})\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
