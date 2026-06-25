from __future__ import annotations

from src.guide_ingest.schemas import ExtractedQuestion, ExtractGuideResult, FigureBBox


def compute_chunk_ranges(
    total_pages: int, chunk_size: int, overlap: int = 1
) -> list[tuple[int, int]]:
    """Split `total_pages` into [start, end) ranges (0-based, end exclusive) of at most
    `chunk_size` pages, each overlapping the previous by `overlap` pages so a question
    split across a boundary is seen whole in at least one chunk (ADR v9 A6.1)."""
    if total_pages <= 0:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    step = max(1, chunk_size - max(0, overlap))
    ranges: list[tuple[int, int]] = []
    start = 0
    while start < total_pages:
        end = min(start + chunk_size, total_pages)
        ranges.append((start, end))
        if end >= total_pages:
            break
        start += step
    return ranges


def offset_pages(result: ExtractGuideResult, page_offset: int) -> ExtractGuideResult:
    """Shift every figure bbox page by `page_offset` so chunk-relative pages become
    absolute pages in the source PDF (the extractor only sees the chunk)."""
    return ExtractGuideResult(
        questions=[
            ExtractedQuestion(
                label=q.label,
                statement_latex=q.statement_latex,
                statement_text=q.statement_text,
                provided_answer=q.provided_answer,
                provided_solution_latex=q.provided_solution_latex,
                figure_bboxes=[
                    FigureBBox(
                        page=b.page + page_offset,
                        x0=b.x0,
                        y0=b.y0,
                        x1=b.x1,
                        y1=b.y1,
                    )
                    for b in q.figure_bboxes
                ],
                continues_previous=q.continues_previous,
            )
            for q in result.questions
        ]
    )
