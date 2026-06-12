from __future__ import annotations

from src.submission_grader.domain import (
    cache_key,
    is_legible,
    latex_steps,
    summarize_alignment,
    transcription_latex,
)
from src.submission_grader.schemas import (
    AlignMatch,
    Alignment,
    AlignVerdict,
    Provisional,
    TranscribeAndAlign,
    Transcription,
    TranscriptionStep,
)


def _transcription(**over: object) -> Transcription:
    base: dict[str, object] = {
        "steps": [
            TranscriptionStep(idx=0, latex="2+2"),
            TranscriptionStep(idx=1, latex="=5", legible=False),
        ],
        "final_answer": "5",
        "confidence": 0.9,
    }
    base.update(over)
    return Transcription(**base)  # type: ignore[arg-type]


def test_cache_key_is_guide_question_version() -> None:
    assert cache_key("g1", "q1", 3) == "g1:q1:v3"


def test_is_legible_respects_floor() -> None:
    assert is_legible(_transcription(confidence=0.5), 0.5) is True
    assert is_legible(_transcription(confidence=0.49), 0.5) is False


def test_transcription_latex_only_legible_steps() -> None:
    assert transcription_latex(_transcription()) == "2+2"


def test_latex_steps_keeps_all_steps_in_order() -> None:
    assert latex_steps(_transcription()) == ["2+2", "=5"]


def test_summarize_alignment_finds_first_error_checkpoint() -> None:
    result = TranscribeAndAlign(
        transcription=_transcription(),
        alignment=Alignment(
            path="MAIN",
            matches=[
                AlignMatch(
                    student_step_idx=0,
                    solution_checkpoint_idx=0,
                    verdict=AlignVerdict.OK,
                ),
                AlignMatch(
                    student_step_idx=1,
                    solution_checkpoint_idx=2,
                    verdict=AlignVerdict.ERROR,
                ),
            ],
        ),
        provisional=Provisional(
            is_correct=False,
            score_0_1=0.5,
            first_error_step_idx=1),
    )
    summary = summarize_alignment(result)
    assert summary.path == "MAIN"
    assert summary.first_error_checkpoint == 2
    assert summary.score_0_1 == 0.5


def test_summarize_alignment_no_error_is_none() -> None:
    result = TranscribeAndAlign(
        transcription=_transcription(),
        alignment=Alignment(
            path="MAIN",
            matches=[
                AlignMatch(
                    student_step_idx=0,
                    solution_checkpoint_idx=0,
                    verdict=AlignVerdict.OK,
                )
            ],
        ),
        provisional=Provisional(is_correct=True, score_0_1=1.0),
    )
    assert summarize_alignment(result).first_error_checkpoint is None
