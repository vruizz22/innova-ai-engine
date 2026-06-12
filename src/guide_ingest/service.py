from __future__ import annotations

import structlog

from src.guide_ingest.chunking import compute_chunk_ranges, offset_pages
from src.guide_ingest.merge import merge_chunks
from src.guide_ingest.ports import (
    GuideExtractorPort,
    GuideRepositoryPort,
    MessagePublisherPort,
    ObjectStorePort,
    PdfPrecheckPort,
    PdfProcessorPort,
)
from src.guide_ingest.schemas import (
    ExtractGuideResult,
    GuideIngestMessage,
    IngestOutcome,
    PrecheckResult,
    SolutionGenMessage,
)
from src.guide_ingest.tex import render_guide_tex
from src.shared.settings import Settings

logger = structlog.get_logger()

_EXTRACTION_MODEL = "claude-sonnet-4-6"


def _failure_reason(precheck: PrecheckResult) -> str:
    if precheck.notes:
        return precheck.notes
    return (
        f"PDF quality {precheck.quality:.2f} below threshold — "
        "rescan at 300dpi and re-upload."
    )


async def ingest_guide(
    message: GuideIngestMessage,
    *,
    precheck: PdfPrecheckPort,
    extractor: GuideExtractorPort,
    pdf: PdfProcessorPort,
    store: ObjectStorePort,
    publisher: MessagePublisherPort,
    repo: GuideRepositoryPort,
    settings: Settings,
) -> IngestOutcome:
    """Orchestrate one guide: precheck -> (terminate or) chunked Sonnet extraction ->
    merge -> crop figures + render .tex to S3 -> persist questions -> enqueue A7.

    Pure of any concrete SDK: every side effect goes through an injected port, so the
    whole flow is unit-testable with fakes (ADR v9 A6)."""
    trace_id = message.trace_id
    await repo.mark_extracting(message.guide_id)

    pdf_bytes = store.get(message.source_pdf_key)
    total_pages = pdf.page_count(pdf_bytes)

    precheck_result = await precheck.precheck(pdf_bytes, trace_id=trace_id)
    if precheck_result.quality < settings.guide_min_extraction_quality:
        reason = _failure_reason(precheck_result)
        await repo.mark_failed(
            message.guide_id,
            source_kind=precheck_result.kind.value,
            pages=total_pages,
            reason=reason,
        )
        logger.warning(
            "guide_extraction_failed",
            guide_id=message.guide_id,
            quality=precheck_result.quality,
            trace_id=trace_id,
        )
        return IngestOutcome(
            guide_id=message.guide_id,
            status="EXTRACTION_FAILED",
            failure_reason=reason,
        )

    ranges = compute_chunk_ranges(
        total_pages,
        settings.guide_ingest_chunk_pages,
        settings.guide_ingest_chunk_overlap,
    )
    chunk_results: list[ExtractGuideResult] = []
    for start, end in ranges:
        chunk_bytes = pdf.slice_pages(pdf_bytes, start, end)
        result = await extractor.extract_chunk(
            chunk_bytes,
            grade_level=message.course_grade_level,
            page_count=end - start,
            trace_id=trace_id,
        )
        chunk_results.append(offset_pages(result, start))

    questions = merge_chunks(chunk_results)

    for question in questions:
        for index, bbox in enumerate(question.figure_bboxes):
            png = pdf.crop_figure(pdf_bytes, bbox)
            key = f"guides/{message.guide_id}/figures/q{question.sequence}_{index}.png"
            store.put(key, png, content_type="image/png")
            question.figure_keys.append(key)

    latex_key = f"guides/{message.guide_id}/guide.tex"
    store.put(
        latex_key,
        render_guide_tex(message.guide_id, questions).encode("utf-8"),
        content_type="application/x-tex",
    )

    await repo.complete(
        message.guide_id,
        questions,
        source_kind=precheck_result.kind.value,
        pages=total_pages,
        latex_key=latex_key,
        extraction_confidence=precheck_result.quality,
        extraction_model=_EXTRACTION_MODEL,
    )

    publisher.publish(
        settings.sqs_solution_gen_url,
        SolutionGenMessage(
            guide_id=message.guide_id,
            guide_question_id=None,
            trace_id=trace_id).model_dump_json(),
        trace_id=trace_id,
    )

    logger.info(
        "guide_ingested",
        guide_id=message.guide_id,
        questions=len(questions),
        trace_id=trace_id,
    )
    return IngestOutcome(
        guide_id=message.guide_id,
        status="GENERATING_SOLUTIONS",
        question_count=len(questions),
    )
