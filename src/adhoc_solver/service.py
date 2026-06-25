from __future__ import annotations

import structlog

from src.adhoc_solver.domain import answers_match, pick_error_tag
from src.adhoc_solver.ports import AdhocRepositoryPort
from src.adhoc_solver.schemas import AdhocSolveMessage, AdhocSolveOutcome
from src.shared.settings import Settings
from src.solution_gen.domain import index_candidates
from src.solution_gen.ports import SolutionGeneratorPort
from src.solution_gen.schemas import GenerationMode, QuestionToSolve

logger = structlog.get_logger()

_GENERATION_MODEL = "claude-sonnet-4-6"
_CORRECT_TAG = "CORRECT"
_UNKNOWN_TAG = "UNKNOWN_ERROR"


async def solve_adhoc(
    message: AdhocSolveMessage,
    *,
    generator: SolutionGeneratorPort,
    repo: AdhocRepositoryPort,
    settings: Settings,
) -> AdhocSolveOutcome:
    """Derive the canonical solution for an ad-hoc (guide-less) exercise scan,
    compare the student's answer, and write the classification result back to the
    `attempts` row.

    Uses the solution_generator in FULL mode (no provided answer in the PDF), then
    compares student's `final_answer` against the derived `gen.final_answer`. If wrong,
    picks the first domain-allowed expected_error_tag; if none, falls back to the domain
    default (UNKNOWN_ERROR).

    Pure of any concrete SDK/DB — all side effects go through injected ports."""
    trace_id = message.trace_id
    attempt_id = message.attempt_id

    candidates = await repo.fetch_taxonomy_candidates(message.grade_level)
    if not candidates:
        logger.warning(
            "adhoc_no_taxonomy_candidates",
            attempt_id=attempt_id,
            grade_level=message.grade_level,
            trace_id=trace_id,
        )
        await repo.mark_attempt_failed(attempt_id, reason="no taxonomy candidates for grade level")
        return AdhocSolveOutcome(
            attempt_id=attempt_id,
            status="FAILED",
            failure_reason="no taxonomy candidates",
        )

    question = QuestionToSolve(
        question_id=attempt_id,
        sequence=1,
        statement_latex=message.problem_latex,
    )

    gen = await generator.generate(
        question,
        mode=GenerationMode.FULL,
        grade_level=message.grade_level,
        topic_candidates=candidates,
        trace_id=trace_id,
    )

    candidate_index = index_candidates(candidates)
    candidate = candidate_index.get(gen.topic_code) if gen.topic_code else None
    domain_id = candidate.domain_id if candidate else None
    subdomain_code = candidate.code if candidate else None

    allowed: set[str] = await repo.fetch_active_error_codes(domain_id) if domain_id else set()

    is_correct = answers_match(gen.final_answer, message.student_final_answer)

    error_tag_code: str
    if is_correct:
        error_tag_code = _CORRECT_TAG
    else:
        picked = pick_error_tag(gen, allowed)
        error_tag_code = picked if picked else _UNKNOWN_TAG

    error_tag_id = await repo.fetch_error_tag_id(error_tag_code)

    await repo.update_attempt_classified(
        attempt_id,
        is_correct=is_correct,
        error_tag_id=error_tag_id,
        domain_id=domain_id,
        subdomain_code=subdomain_code,
        derived_answer=gen.final_answer,
        model=_GENERATION_MODEL,
    )

    logger.info(
        "adhoc_solve_done",
        attempt_id=attempt_id,
        is_correct=is_correct,
        derived_answer=gen.final_answer,
        student_answer=message.student_final_answer,
        error_tag_code=error_tag_code,
        topic_code=gen.topic_code,
        trace_id=trace_id,
    )

    return AdhocSolveOutcome(
        attempt_id=attempt_id,
        is_correct=is_correct,
        derived_answer=gen.final_answer,
        error_tag_code=error_tag_code,
        status="CLASSIFIED",
    )
