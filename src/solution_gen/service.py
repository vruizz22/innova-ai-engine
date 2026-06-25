from __future__ import annotations

import json

import structlog

from src.guide_ingest.schemas import SolutionGenMessage
from src.observability.metrics import M_NEEDS_REVIEW_RATIO, UNIT_NONE, emit_metrics
from src.shared.settings import Settings
from src.solution_gen.domain import (
    STATUS_REVIEW,
    collect_error_tags,
    decide_mode,
    index_candidates,
    resolve_status,
    sanitize_solution,
    solution_source,
)
from src.solution_gen.ports import SolutionGeneratorPort, SolutionRepositoryPort
from src.solution_gen.prompts import PROMPT_VERSION
from src.solution_gen.schemas import GeneratedSolution, GuideSolveOutcome, SolutionStep

logger = structlog.get_logger()

_GENERATION_MODEL = "claude-sonnet-4-6"


def _canonical_steps(steps: list[SolutionStep]) -> list[dict[str, object]]:
    """Stamp each step with its 0-based `idx` (ADR-118 requires it; the Pydantic
    model omits it because order is implicit in the list)."""
    return [{"idx": i, **step.model_dump()} for i, step in enumerate(steps)]


def _steps_json(gen: GeneratedSolution, *, points: float) -> str:
    """Canonical ADR-118 document persisted to `guide_solutions.steps_json`.

    The contract is enforced by BOTH ends — backend `canonicalSolutionSchema`
    (guide-state-machine.ts) on teacher save AND the frontend Zod on read — so the
    top-level `final_answer`/`points` and the per-step `idx` MUST be embedded here;
    without them the review wizard's `getGuide` parse fails ("No pudimos cargar la guía")."""
    return json.dumps(
        {
            "final_answer": gen.final_answer,
            "points": points,
            "steps": _canonical_steps(gen.steps),
            "alt_paths": [
                {"label": path.label, "steps": _canonical_steps(path.steps)}
                for path in gen.alt_paths
            ],
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
        logger.warning("solution_gen_no_questions", guide_id=message.guide_id, trace_id=trace_id)
        return GuideSolveOutcome(guide_id=message.guide_id, processed=0)

    candidates = await repo.fetch_taxonomy_candidates(ctx.grade_level)
    candidate_index = index_candidates(candidates)

    processed = 0
    needs_review = 0
    for question in ctx.questions:
        mode = decide_mode(question.provided_solution_latex, question.provided_answer)
        gen = await generator.generate(
            question,
            mode=mode,
            grade_level=ctx.grade_level,
            topic_candidates=candidates,
            trace_id=trace_id,
        )

        candidate = candidate_index.get(gen.topic_code) if gen.topic_code else None
        domain_id = candidate.domain_id if candidate else None
        allowed = await repo.fetch_active_error_codes(domain_id) if domain_id else set[str]()
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
            steps_json=_steps_json(clean, points=question.points),
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
    if processed > 0:
        emit_metrics(
            [(M_NEEDS_REVIEW_RATIO, needs_review / processed, UNIT_NONE)],
            guide_id=message.guide_id,
            trace_id=trace_id,
        )
    return GuideSolveOutcome(
        guide_id=message.guide_id,
        processed=processed,
        needs_review_count=needs_review,
        guide_status=guide_status,
        alert_created=alert_created,
    )
