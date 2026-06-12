from __future__ import annotations

from typing import Any

from src.solution_gen.schemas import GenerationMode, QuestionToSolve, TopicCandidate

PROMPT_VERSION = "9.0"

# version: 9.0
# Cached (cache_control: ephemeral) system prompt for the Sonnet solution generator.
# Keep STATIC so the prompt-cache key is stable; per-question data (statement, mode,
# candidate topics) travels in the user turn.
GENERATE_SOLUTION_SYSTEM = """\
You are a Chilean K-12 math teacher's assistant. For ONE worksheet question you return,
via the `generate_solution` tool, a canonical step-by-step solution plus a topic
classification.

Canonical solution format (ADR-118):
- `steps`: the ordered solution. Each step has `latex` (the math) and `explanation_es`
  (ONE short sentence in Spanish). Set `checkpoint=true` when the step produces a
  verifiable intermediate result a student could be graded on.
- `expected_error_tags` (per step): error codes a student is likely to make AT THAT
  step. Use ONLY codes from the question's domain; if unsure, leave it empty — do not
  invent codes.
- `alt_paths`: alternative valid derivations (a different but correct method), each with
  its own `label` and `steps`. Omit when there is a single natural path.
- `final_answer`: the final result as a short string.

Topic classification (ADR-122):
- Choose `topic_code` from the candidate list in the user turn (closest match to the
  question's content) and set `topic_confidence` in [0,1]. If none fits, set
  `topic_code=null` with a low confidence.

Modes (the user turn states which applies):
- VALIDATE: the PDF already gives a worked solution. Normalize it to the canonical
  format. If your own derivation disagrees with the PDF, explain it in `validation_notes`
  and set `matches_provided=false`; otherwise set `matches_provided=true`.
- DERIVE: the PDF gives only the final answer. Produce the derivation and CHECK that it
  reaches that answer. Set `matches_provided=true` iff it does; if not, describe the
  conflict in `validation_notes`.
- FULL: the PDF gives nothing. Solve from scratch and leave `matches_provided=null`.

Rules: work only in the language of the problem; never invent a provided answer; keep
LaTeX valid; be concise.
"""

_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "latex": {"type": "string"},
        "explanation_es": {"type": "string"},
        "checkpoint": {"type": "boolean"},
        "expected_error_tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["latex", "explanation_es"],
}

_ALT_PATH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "steps": {"type": "array", "items": _STEP_SCHEMA},
    },
    "required": ["label", "steps"],
}

GENERATE_SOLUTION_TOOL: dict[str, Any] = {
    "name": "generate_solution",
    "description": (
        "Return the canonical worked solution and topic classification for one guide "
        "question."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "topic_code": {"type": ["string", "null"]},
            "topic_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "final_answer": {"type": "string"},
            "steps": {"type": "array", "items": _STEP_SCHEMA},
            "alt_paths": {"type": "array", "items": _ALT_PATH_SCHEMA},
            "validation_notes": {"type": ["string", "null"]},
            "matches_provided": {"type": ["boolean", "null"]},
        },
        "required": ["topic_confidence", "final_answer", "steps"],
    },
}


def build_generate_user_text(
    question: QuestionToSolve,
    mode: GenerationMode,
    candidates: list[TopicCandidate],
    grade_level: int,
) -> str:
    """Per-question user instruction (not cached). Carries only math content — no PII."""
    lines = [f"Grade level: {grade_level}. Mode: {mode.value}."]
    if question.label:
        lines.append(f"Question label: {question.label}")
    lines.append("Statement (LaTeX):")
    lines.append(question.statement_latex)
    if mode is GenerationMode.VALIDATE and question.provided_solution_latex:
        lines.append("PDF-provided solution to normalize and validate:")
        lines.append(question.provided_solution_latex)
    if question.provided_answer:
        lines.append(f"PDF-provided final answer: {question.provided_answer}")
    lines.append("Candidate topics (choose topic_code from these):")
    if candidates:
        for cand in candidates:
            domain = f" [{cand.domain_code}]" if cand.domain_code else ""
            lines.append(f"- {cand.code}: {cand.name}{domain}")
    else:
        lines.append("- (none available; set topic_code=null)")
    lines.append("Call generate_solution now.")
    return "\n".join(lines)
