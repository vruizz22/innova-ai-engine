from __future__ import annotations

from src.solution_gen.schemas import (
    GeneratedSolution,
    GenerationMode,
    SolutionStep,
    TopicCandidate,
)

# GuideQuestionStatus values A7 may write (APPROVED/EXCLUDED are teacher-only).
STATUS_OK = "EXTRACTED"  # pipeline-done, unreviewed, no weak signal
STATUS_REVIEW = "NEEDS_REVIEW"  # flagged for the teacher's attention

# SolutionSource values (Prisma enum).
SOURCE_PDF = "PDF_PROVIDED"  # VALIDATE normalizes the PDF's own solution
SOURCE_LLM = "LLM_GENERATED"  # DERIVE/FULL are model-authored


def decide_mode(
    provided_solution_latex: str | None, provided_answer: str | None
) -> GenerationMode:
    """Pick the generation mode from what the extraction carried (ADR v9 A7.1)."""
    if provided_solution_latex and provided_solution_latex.strip():
        return GenerationMode.VALIDATE
    if provided_answer and provided_answer.strip():
        return GenerationMode.DERIVE
    return GenerationMode.FULL


def grade_window(grade_level: int) -> tuple[int, int]:
    """Topic search window: course grade ±1, clamped to grade >= 1 (ADR-122)."""
    return (max(1, grade_level - 1), grade_level + 1)


def solution_source(mode: GenerationMode) -> str:
    """VALIDATE keeps provenance on the PDF; DERIVE/FULL are model-authored."""
    return SOURCE_PDF if mode is GenerationMode.VALIDATE else SOURCE_LLM


def index_candidates(
        candidates: list[TopicCandidate]) -> dict[str, TopicCandidate]:
    """code -> candidate; first occurrence wins (curriculum-version dedupe)."""
    index: dict[str, TopicCandidate] = {}
    for cand in candidates:
        index.setdefault(cand.code, cand)
    return index


def _sanitize_steps(steps: list[SolutionStep],
                    allowed: set[str]) -> list[SolutionStep]:
    cleaned: list[SolutionStep] = []
    for step in steps:
        tags = [tag for tag in step.expected_error_tags if tag in allowed]
        cleaned.append(step.model_copy(update={"expected_error_tags": tags}))
    return cleaned


def sanitize_solution(gen: GeneratedSolution,
                      allowed: set[str]) -> GeneratedSolution:
    """Return a copy whose every step's `expected_error_tags` are constrained to the
    resolved domain's ACTIVE catalog (ADR v9 A7.2). Guarantees stored tags are real
    codes even when the model hallucinates; an empty `allowed` (unresolved domain)
    clears all tags."""
    steps = _sanitize_steps(gen.steps, allowed)
    alt_paths = [
        path.model_copy(update={"steps": _sanitize_steps(path.steps, allowed)})
        for path in gen.alt_paths
    ]
    return gen.model_copy(update={"steps": steps, "alt_paths": alt_paths})


def collect_error_tags(gen: GeneratedSolution) -> list[str]:
    """De-duplicated, order-preserving union of every main-path step's error tags —
    persisted to `guide_solutions.expected_error_tags`."""
    tags: list[str] = []
    seen: set[str] = set()
    for step in gen.steps:
        for tag in step.expected_error_tags:
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return tags


def resolve_status(
    mode: GenerationMode,
    gen: GeneratedSolution,
    *,
    topic_resolved: bool,
    min_topic_confidence: float,
) -> str:
    """A question is flagged NEEDS_REVIEW when any signal is weak; otherwise it stays
    EXTRACTED (pipeline-done, unreviewed). Rules (ADR v9 A7.1/A7.2):

    - topic unresolved or `topic_confidence < threshold` -> NEEDS_REVIEW
    - FULL mode (nothing came from the PDF) -> always NEEDS_REVIEW
    - VALIDATE/DERIVE that didn't reach the PDF's answer -> NEEDS_REVIEW
    - an explicit `validation_notes` discrepancy -> NEEDS_REVIEW
    """
    if not topic_resolved or gen.topic_confidence < min_topic_confidence:
        return STATUS_REVIEW
    if mode is GenerationMode.FULL:
        return STATUS_REVIEW
    if gen.matches_provided is False:
        return STATUS_REVIEW
    if gen.validation_notes and gen.validation_notes.strip():
        return STATUS_REVIEW
    return STATUS_OK
