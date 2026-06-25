from __future__ import annotations

from src.guide_ingest.schemas import ExtractGuideResult, MergedQuestion


def _norm(text: str) -> str:
    """Whitespace/case-insensitive key for overlap-duplicate detection."""
    return " ".join(text.lower().split())


def merge_chunks(chunk_results: list[ExtractGuideResult]) -> list[MergedQuestion]:
    """Flatten per-chunk extractions into the final ordered question list, resolving the
    1-page overlap between chunks (ADR v9 A6.1):

    - a chunk's FIRST question with `continues_previous=True` is stitched onto the
      previous chunk's last question (the boundary split it);
    - a chunk's first question that duplicates the previous question's statement (the
      overlap page re-extracted it) is dropped.

    Sequence numbers are assigned 1..N at the end."""
    merged: list[MergedQuestion] = []

    for result in chunk_results:
        for index, question in enumerate(result.questions):
            is_chunk_head = index == 0
            if is_chunk_head and merged:
                previous = merged[-1]
                if question.continues_previous:
                    previous.statement_latex = (
                        f"{previous.statement_latex}\n{question.statement_latex}".strip()
                    )
                    previous.statement_text = (
                        f"{previous.statement_text} {question.statement_text}".strip()
                    )
                    previous.figure_bboxes.extend(question.figure_bboxes)
                    if previous.provided_answer is None:
                        previous.provided_answer = question.provided_answer
                    if previous.provided_solution_latex is None:
                        previous.provided_solution_latex = question.provided_solution_latex
                    continue
                if _norm(question.statement_text) == _norm(previous.statement_text):
                    continue

            merged.append(
                MergedQuestion(
                    sequence=len(merged) + 1,
                    label=question.label,
                    statement_latex=question.statement_latex,
                    statement_text=question.statement_text,
                    provided_answer=question.provided_answer,
                    provided_solution_latex=question.provided_solution_latex,
                    figure_bboxes=list(question.figure_bboxes),
                    figure_keys=[],
                )
            )

    return merged
