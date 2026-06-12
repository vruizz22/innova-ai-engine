from __future__ import annotations

from src.guide_ingest.merge import merge_chunks
from src.guide_ingest.schemas import ExtractedQuestion, ExtractGuideResult


def _q(
    text: str,
    *,
    continues: bool = False,
    answer: str | None = None,
) -> ExtractedQuestion:
    return ExtractedQuestion(
        statement_latex=text,
        statement_text=text,
        continues_previous=continues,
        provided_answer=answer,
    )


def test_assigns_sequence() -> None:
    merged = merge_chunks([ExtractGuideResult(questions=[_q("a"), _q("b")])])
    assert [m.sequence for m in merged] == [1, 2]


def test_stitches_continuation_across_chunks() -> None:
    chunk1 = ExtractGuideResult(questions=[_q("Q1 part"), _q("Q2 head")])
    chunk2 = ExtractGuideResult(
        questions=[_q("Q2 tail", continues=True, answer="42"), _q("Q3")]
    )
    merged = merge_chunks([chunk1, chunk2])
    assert len(merged) == 3
    assert "Q2 head" in merged[1].statement_text
    assert "Q2 tail" in merged[1].statement_text
    assert merged[1].provided_answer == "42"
    assert [m.sequence for m in merged] == [1, 2, 3]


def test_drops_overlap_duplicate() -> None:
    chunk1 = ExtractGuideResult(questions=[_q("Q1"), _q("Q2 overlap")])
    chunk2 = ExtractGuideResult(questions=[_q("Q2 overlap"), _q("Q3")])
    merged = merge_chunks([chunk1, chunk2])
    assert [m.statement_text for m in merged] == ["Q1", "Q2 overlap", "Q3"]
