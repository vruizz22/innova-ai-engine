from __future__ import annotations

from src.submission_grader.schemas import (
    AlignmentSummary,
    AlignVerdict,
    TranscribeAndAlign,
    Transcription,
)

# SubmissionStatus values A8 may write.
STATUS_GRADING = "GRADING"  # provisional verdict written, handed to reprocess
STATUS_GRADED = "GRADED"  # terminal here only for the ILLEGIBLE fallback
STATUS_FAILED = "FAILED"

ILLEGIBLE_REASON = "ILLEGIBLE"
PROVIDER = "claude-haiku"


def cache_key(guide_id: str, question_id: str, solution_version: int) -> str:
    """Logical cache identity of the per-question cached block (guide, question,
    solutionVersion) — the ~35 submissions of a question share it (ADR v9 A8.1)."""
    return f"{guide_id}:{question_id}:v{solution_version}"


def is_legible(transcription: Transcription, min_confidence: float) -> bool:
    """A transcription is usable when its overall confidence clears the floor."""
    return transcription.confidence >= min_confidence


def transcription_latex(transcription: Transcription) -> str:
    """Newline-joined LaTeX of the legible steps — stored on the submission row."""
    return "\n".join(step.latex for step in transcription.steps if step.legible)


def latex_steps(transcription: Transcription) -> list[str]:
    """Every step's LaTeX, in order — the payload the rule engine re-processes."""
    return [step.latex for step in transcription.steps]


def aligned_latex_steps(result: TranscribeAndAlign) -> list[str]:
    """Return only the steps the grader aligned to the question's solution.

    When the student submits a full-page scan the transcription contains work from
    multiple exercises. The grader's alignment.matches identifies which student step
    indices belong to the graded question; steps not present in matches belong to
    other exercises and must not reach the LLM classifier (they cause spurious
    TASK_SWITCHING errors).  Falls back to all steps when the alignment has no
    matches at all (e.g., the grader returned UNALIGNED with an empty matches list).
    """
    matched_indices = {m.student_step_idx for m in result.alignment.matches}
    if not matched_indices:
        return latex_steps(result.transcription)
    return [step.latex for step in result.transcription.steps if step.idx in matched_indices]


def summarize_alignment(result: TranscribeAndAlign) -> AlignmentSummary:
    """Compact digest for the reprocess queue: path, the solution checkpoint of the first
    ERROR (or None), and the provisional score."""
    first_error: int | None = None
    for match in result.alignment.matches:
        if match.verdict is AlignVerdict.ERROR:
            first_error = match.solution_checkpoint_idx
            break
    return AlignmentSummary(
        path=result.alignment.path,
        first_error_checkpoint=first_error,
        score_0_1=result.provisional.score_0_1,
    )
