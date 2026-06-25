from __future__ import annotations

import structlog

from src.exercise_generator.ports import (
    ExerciseRepositoryPort,
    GeneratorError,
    LlmExerciseGeneratorPort,
    SubdomainNotFoundError,
)
from src.exercise_generator.schemas import (
    GenerateExercisesMessage,
    GenerateExercisesResult,
)
from src.observability.cost import cost_usd

logger = structlog.get_logger()

_WORKER = "exercise_generator"


async def generate_exercises(
    message: GenerateExercisesMessage,
    *,
    generator: LlmExerciseGeneratorPort,
    repo: ExerciseRepositoryPort,
) -> GenerateExercisesResult:
    """Generate and persist AI-authored exercises for one subdomain.

    Pure of concrete SDK/DB — all side effects go through injected ports. Terminal
    on `GeneratorError` (no retry); warn-and-continue on per-exercise validation errors
    so a bad item doesn't block the whole batch."""
    trace_id = message.trace_id
    log = logger.bind(
        trace_id=trace_id,
        subdomain_code=message.subdomain_code,
        count=message.count,
    )

    subdomain = await repo.load_subdomain(message.subdomain_code)
    if subdomain is None and message.target_error_codes:
        first_code = message.target_error_codes[0]
        subdomain = await repo.load_subdomain_for_error_code(first_code)
        if subdomain is not None:
            log.warning(
                "exercise_generator.subdomain_resolved_from_error_code",
                requested=message.subdomain_code,
                resolved_via=first_code,
            )
    if subdomain is None:
        raise SubdomainNotFoundError(f"Subdomain not found: {message.subdomain_code}")
    subdomain_id, subdomain_description = subdomain

    topic_id = await repo.topic_id_for_subdomain(subdomain_id)
    if topic_id is None:
        raise GeneratorError(f"No topic mapped for subdomain: {message.subdomain_code}")

    error_descriptions_map = await repo.load_error_descriptions(message.target_error_codes)
    error_descriptions = [
        error_descriptions_map.get(code, code) for code in message.target_error_codes
    ]

    exercises, usage = await generator.generate(
        subdomain_code=message.subdomain_code,
        subdomain_description=subdomain_description,
        grade_level=message.grade_level,
        target_error_codes=message.target_error_codes,
        error_descriptions=error_descriptions,
        count=message.count,
        trace_id=trace_id,
    )

    log.info("exercise_generator.generated", raw_count=len(exercises))

    persisted = 0
    for ex in exercises:
        duplicate = await repo.problem_exists(ex.problem_latex, subdomain_id)
        if duplicate:
            log.info("exercise_generator.dedup_skip", problem=ex.problem_latex[:60])
            continue
        try:
            await repo.persist_exercise(
                topic_id=topic_id,
                problem_latex=ex.problem_latex,
                correct_answer_latex=ex.correct_answer_latex,
                solution_steps_latex=ex.solution_steps_latex,
                irt_a=ex.irt_a,
                irt_b=ex.irt_b,
                target_error_codes=ex.target_error_codes,
            )
            persisted += 1
        except Exception:
            log.warning("exercise_generator.persist_error", problem=ex.problem_latex[:60])

    usd = cost_usd(usage, model="claude-haiku-4-5")
    try:
        await repo.save_cost_event(
            worker=_WORKER,
            model="claude-haiku-4-5",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_creation_input_tokens=usage.cache_creation_input_tokens,
            cache_read_input_tokens=usage.cache_read_input_tokens,
            cost_usd=usd,
            trace_id=trace_id,
        )
    except Exception:
        log.warning("exercise_generator.cost_event_failed", trace_id=trace_id)

    log.info(
        "exercise_generator.done",
        generated=len(exercises),
        persisted=persisted,
        cost_usd=round(usd, 6),
    )
    return GenerateExercisesResult(
        subdomain_code=message.subdomain_code,
        requested=message.count,
        generated=len(exercises),
        persisted=persisted,
    )
