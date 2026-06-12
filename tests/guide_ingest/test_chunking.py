from __future__ import annotations

import pytest

from src.guide_ingest.chunking import compute_chunk_ranges, offset_pages
from src.guide_ingest.schemas import ExtractedQuestion, ExtractGuideResult, FigureBBox


def test_single_chunk_when_within_size() -> None:
    assert compute_chunk_ranges(5, 20, 1) == [(0, 5)]


def test_zero_pages_returns_empty() -> None:
    assert compute_chunk_ranges(0, 20, 1) == []


def test_overlap_ranges() -> None:
    assert compute_chunk_ranges(45, 20, 1) == [(0, 20), (19, 39), (38, 45)]


def test_no_overlap_ranges() -> None:
    assert compute_chunk_ranges(40, 20, 0) == [(0, 20), (20, 40)]


def test_invalid_chunk_size_raises() -> None:
    with pytest.raises(ValueError):
        compute_chunk_ranges(10, 0, 1)


def test_offset_pages_shifts_and_is_pure() -> None:
    result = ExtractGuideResult(
        questions=[
            ExtractedQuestion(
                statement_latex="x",
                statement_text="x",
                figure_bboxes=[
                    FigureBBox(
                        page=0,
                        x0=0.1,
                        y0=0.1,
                        x1=0.2,
                        y1=0.2)],
            )])
    shifted = offset_pages(result, 19)
    assert shifted.questions[0].figure_bboxes[0].page == 19
    # original is untouched
    assert result.questions[0].figure_bboxes[0].page == 0
