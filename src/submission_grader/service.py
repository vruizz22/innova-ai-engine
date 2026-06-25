from __future__ import annotations

import json

import structlog

from src.guide_ingest.ports import MessagePublisherPort, ObjectStorePort
from src.observability.cost import TokenUsage, cost_usd
from src.observability.metrics import (
    M_CACHE_HIT_RATE,
    M_COST_PER_SUBMISSION,
    M_ILLEGIBLE_RATE,
    M_UNALIGNED_RATE,
    UNIT_NONE,
    emit_metrics,
)
from src.shared.settings import Settings
from src.submission_grader.domain import (
    ILLEGIBLE_REASON,
    PROVIDER,
    STATUS_FAILED,
    STATUS_GRADED,
    STATUS_GRADING,
    aligned_latex_steps,
    is_legible,
    summarize_alignment,
    transcription_latex,
)
from src.submission_grader.ports import (
    GraderResponseError,
    SubmissionGraderPort,
    SubmissionRepositoryPort,
)
from src.submission_grader.schemas import (
    GradeOutcome,
    GradeSubmissionMessage,
    ReprocessMessage,
    SubmissionContext,
    TranscribeAndAlign,
)

logger = structlog.get_logger()

_MODEL = "claude-haiku-4-5"

# Stored on the submission when the grader's response is unreadable/unparseable. Terminal:
# the photo is re-uploadable by the student, but this attempt is not retried (cost guard).
GRADER_RESPONSE_FAILURE = "GRADER_RESPONSE_INVALID"


def _alignment_json(result: TranscribeAndAlign) -> str:
    return json.dumps(
        {
            "alignment": result.alignment.model_dump(),
            "provisional": result.provisional.model_dump(),
        }
    )


async def grade_submission(
    message: GradeSubmissionMessage,
    *,
    grader: SubmissionGraderPort,
    store: ObjectStorePort,
    publisher: MessagePublisherPort,
    repo: SubmissionRepositoryPort,
    settings: Settings,
) -> GradeOutcome:
    """Grade one handwritten submission: load photos + current pauta, run Haiku vision
    (one retry on low confidence), persist transcription/alignment/provisional score and
    hand off to the existing reprocess queue. Illegible after retry closes GRADED with an
    ILLEGIBLE note (no reprocess).

    Pure of any concrete SDK/DB: every side effect goes through an injected port (ADR v9
    A8)."""
    trace_id = message.trace_id
    submission_id = message.guide_submission_id

    ctx = await repo.load_submission_context(submission_id)
    if ctx is None:
        logger.warning("grade_no_context", guide_submission_id=submission_id, trace_id=trace_id)
        return GradeOutcome(
            guide_submission_id=submission_id,
            status=STATUS_FAILED,
            failure_reason="submission or current solution not found",
        )

    images = [store.get(key) for key in ctx.photo_keys]
    if not images:
        await repo.save_grading(
            submission_id,
            status=STATUS_FAILED,
            transcription_latex="",
            transcription_json="{}",
            transcription_confidence=0.0,
            alignment_json=None,
            score=None,
            is_correct=None,
            solution_version=ctx.solution_version,
            model_used=_MODEL,
            failure_reason="no photos",
        )
        return GradeOutcome(
            guide_submission_id=submission_id, status=STATUS_FAILED, failure_reason="no photos"
        )

    min_conf = settings.grading_min_transcription_confidence
    try:
        result, usage = await _grade_with_retry(grader, images, ctx, min_conf, trace_id)
    except GraderResponseError as exc:
        # The grader returned an unreadable response (e.g. a photo it can't parse).
        # Retrying re-bills the same vision call for the same result, so close the
        # submission as FAILED here and let the message be deleted — never redelivered.
        await repo.save_grading(
            submission_id,
            status=STATUS_FAILED,
            transcription_latex="",
            transcription_json="{}",
            transcription_confidence=0.0,
            alignment_json=None,
            score=None,
            is_correct=None,
            solution_version=ctx.solution_version,
            model_used=_MODEL,
            failure_reason=GRADER_RESPONSE_FAILURE,
        )
        logger.error(
            "submission_grade_unreadable",
            guide_submission_id=submission_id,
            error=str(exc),
            trace_id=trace_id,
        )
        return GradeOutcome(
            guide_submission_id=submission_id,
            status=STATUS_FAILED,
            failure_reason=GRADER_RESPONSE_FAILURE,
        )
    submission_cost = cost_usd(usage, _MODEL)

    if not is_legible(result.transcription, min_conf):
        # Terminal ILLEGIBLE: keep the partial transcription for the teacher,
        # no reprocess.
        await repo.save_grading(
            submission_id,
            status=STATUS_GRADED,
            transcription_latex=transcription_latex(result.transcription),
            transcription_json=result.transcription.model_dump_json(),
            transcription_confidence=result.transcription.confidence,
            alignment_json=None,
            score=None,
            is_correct=None,
            solution_version=ctx.solution_version,
            model_used=_MODEL,
            failure_reason=ILLEGIBLE_REASON,
        )
        logger.warning(
            "submission_illegible",
            guide_submission_id=submission_id,
            confidence=result.transcription.confidence,
            trace_id=trace_id,
        )
        emit_metrics(
            [
                (M_ILLEGIBLE_RATE, 1.0, UNIT_NONE),
                (M_UNALIGNED_RATE, 0.0, UNIT_NONE),
                (M_COST_PER_SUBMISSION, submission_cost, UNIT_NONE),
                (M_CACHE_HIT_RATE, usage.cache_hit_rate, UNIT_NONE),
            ],
            guide_submission_id=submission_id,
            trace_id=trace_id,
        )
        await repo.save_cost_event(
            worker="submission_grader",
            model=_MODEL,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_creation_input_tokens=usage.cache_creation_input_tokens,
            cache_read_input_tokens=usage.cache_read_input_tokens,
            cost_usd=submission_cost,
            trace_id=trace_id,
        )
        return GradeOutcome(
            guide_submission_id=submission_id,
            status=STATUS_GRADED,
            illegible=True,
            failure_reason=ILLEGIBLE_REASON,
        )

    summary = summarize_alignment(result)
    await repo.save_grading(
        submission_id,
        status=STATUS_GRADING,
        transcription_latex=transcription_latex(result.transcription),
        transcription_json=result.transcription.model_dump_json(),
        transcription_confidence=result.transcription.confidence,
        alignment_json=_alignment_json(result),
        score=result.provisional.score_0_1,
        is_correct=result.provisional.is_correct,
        solution_version=ctx.solution_version,
        model_used=_MODEL,
        failure_reason=None,
    )
    publisher.publish(
        settings.sqs_attempt_reprocess_url,
        ReprocessMessage(
            guide_submission_id=submission_id,
            guide_question_id=ctx.guide_question_id,
            latex_steps=aligned_latex_steps(result),
            provider=PROVIDER,
            confidence=result.transcription.confidence,
            alignment_summary=summary,
            trace_id=trace_id,
        ).model_dump_json(),
        trace_id=trace_id,
    )
    logger.info(
        "submission_grade_done",
        guide_submission_id=submission_id,
        score=result.provisional.score_0_1,
        path=result.alignment.path,
        trace_id=trace_id,
    )
    unaligned = 1.0 if result.alignment.path == "UNALIGNED" else 0.0
    emit_metrics(
        [
            (M_ILLEGIBLE_RATE, 0.0, UNIT_NONE),
            (M_UNALIGNED_RATE, unaligned, UNIT_NONE),
            (M_COST_PER_SUBMISSION, submission_cost, UNIT_NONE),
            (M_CACHE_HIT_RATE, usage.cache_hit_rate, UNIT_NONE),
        ],
        guide_submission_id=submission_id,
        trace_id=trace_id,
    )
    await repo.save_cost_event(
        worker="submission_grader",
        model=_MODEL,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_input_tokens=usage.cache_creation_input_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens,
        cost_usd=submission_cost,
        trace_id=trace_id,
    )
    return GradeOutcome(
        guide_submission_id=submission_id,
        status=STATUS_GRADING,
        score=result.provisional.score_0_1,
        is_correct=result.provisional.is_correct,
        published=True,
    )


async def _grade_with_retry(
    grader: SubmissionGraderPort,
    images: list[bytes],
    ctx: SubmissionContext,
    min_conf: float,
    trace_id: str,
) -> tuple[TranscribeAndAlign, TokenUsage]:
    """Grade once; retry exactly once when the transcription is below the floor
    (ADR v9 A8.2). Returns the chosen result with the usage of every call made, so a
    retried submission is priced for both calls (A9.4)."""
    result, usage = await _grade_once(grader, images, ctx, trace_id)
    if is_legible(result.transcription, min_conf):
        return result, usage
    retry_result, retry_usage = await _grade_once(grader, images, ctx, trace_id)
    return retry_result, usage + retry_usage


async def _grade_once(
    grader: SubmissionGraderPort,
    images: list[bytes],
    ctx: SubmissionContext,
    trace_id: str,
) -> tuple[TranscribeAndAlign, TokenUsage]:
    return await grader.grade(
        images,
        grade_level=ctx.grade_level,
        question_label=ctx.question_label,
        solution_steps_json=ctx.solution_steps_json,
        solution_final_answer=ctx.solution_final_answer,
        domain_catalog_text=ctx.domain_catalog_text,
        trace_id=trace_id,
    )
