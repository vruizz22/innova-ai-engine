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
    return "\n".join(
        step.latex for step in transcription.steps if step.legible)


def latex_steps(transcription: Transcription) -> list[str]:
    """Every step's LaTeX, in order — the payload the rule engine re-processes."""
    return [step.latex for step in transcription.steps]


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
