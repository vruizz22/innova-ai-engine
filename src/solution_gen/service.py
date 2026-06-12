from __future__ import annotations

import json

import structlog

from src.guide_ingest.schemas import SolutionGenMessage
from src.shared.settings import Settings
from src.solution_gen.domain import (
    STATUS_REVIEW,
    collect_error_tags,
    decide_mode,
    grade_window,
    index_candidates,
    resolve_status,
    sanitize_solution,
    solution_source,
)
from src.solution_gen.ports import SolutionGeneratorPort, SolutionRepositoryPort
from src.solution_gen.prompts import PROMPT_VERSION
from src.solution_gen.schemas import GeneratedSolution, GuideSolveOutcome

logger = structlog.get_logger()

_GENERATION_MODEL = "claude-sonnet-4-6"


def _steps_json(gen: GeneratedSolution) -> str:
    """Canonical ADR-118 document persisted to `guide_solutions.steps_json`."""
    return json.dumps(
        {
            "steps": [step.model_dump() for step in gen.steps],
            "alt_paths": [path.model_dump() for path in gen.alt_paths],
        }
    )


async def generate_solutions(
    message: SolutionGenMessage,
    *,
    generator: SolutionGeneratorPort,
    repo: SolutionRepositoryPort,
    settings: Settings,
) -> GuideSolveOutcome:
    """Generate canonical solutions for a guide's questions (or one, on re-generation):
    per question pick the mode, call Sonnet, classify the topic, constrain error tags to
    the domain catalog, persist; when the whole guide is solved flip it to REVIEW and
    raise a deduped teacher alert.

    Pure of any concrete SDK/DB: every side effect goes through an injected port, so the
    flow is unit-testable with fakes (ADR v9 A7)."""
    trace_id = message.trace_id
    ctx = await repo.load_guide_context(message.guide_id, message.guide_question_id)
    if ctx is None or not ctx.questions:
        logger.warning(
            "solution_gen_no_questions",
            guide_id=message.guide_id,
            trace_id=trace_id)
        return GuideSolveOutcome(guide_id=message.guide_id, processed=0)

    grade_min, grade_max = grade_window(ctx.grade_level)
    candidates = await repo.fetch_topic_candidates(ctx.subject_id, grade_min, grade_max)
    candidate_index = index_candidates(candidates)

    processed = 0
    needs_review = 0
    for question in ctx.questions:
        mode = decide_mode(
            question.provided_solution_latex, question.provided_answer
        )
        gen = await generator.generate(
            question,
            mode=mode,
            grade_level=ctx.grade_level,
            topic_candidates=candidates,
            trace_id=trace_id,
        )

        candidate = (
            candidate_index.get(gen.topic_code) if gen.topic_code else None
        )
        domain_id = candidate.domain_id if candidate else None
        allowed = (
            await repo.fetch_active_error_codes(domain_id) if domain_id else set()
        )
        clean = sanitize_solution(gen, allowed)

        status = resolve_status(
            mode,
            gen,
            topic_resolved=candidate is not None,
            min_topic_confidence=settings.solution_topic_min_confidence,
        )
        await repo.save_solution(
            question.question_id,
            version=question.current_version + 1,
            source=solution_source(mode),
            status=status,
            final_answer=clean.final_answer,
            steps_json=_steps_json(clean),
            solution_latex=None,  # render derived in the wizard, not source of truth
            expected_error_tags=collect_error_tags(clean),
            topic_id=candidate.topic_id if candidate else None,
            domain_id=domain_id,
            subdomain_id=candidate.subdomain_id if candidate else None,
            topic_confidence=gen.topic_confidence,
            validation_notes=clean.validation_notes,
            model=_GENERATION_MODEL,
            prompt_version=PROMPT_VERSION,
        )
        processed += 1
        if status == STATUS_REVIEW:
            needs_review += 1

    unsolved = await repo.count_unsolved(message.guide_id)
    alert_created = False
    guide_status = "GENERATING_SOLUTIONS"
    if unsolved == 0:
        alert_created = await repo.mark_guide_review_and_alert(
            message.guide_id,
            teacher_id=ctx.teacher_id,
            course_id=ctx.course_id,
            title=ctx.title,
            question_count=ctx.question_count,
            needs_review_count=needs_review,
        )
        guide_status = "REVIEW"

    logger.info(
        "solution_gen_done",
        guide_id=message.guide_id,
        processed=processed,
        needs_review=needs_review,
        guide_status=guide_status,
        alert_created=alert_created,
        trace_id=trace_id,
    )
    return GuideSolveOutcome(
        guide_id=message.guide_id,
        processed=processed,
        needs_review_count=needs_review,
        guide_status=guide_status,
        alert_created=alert_created,
    )
