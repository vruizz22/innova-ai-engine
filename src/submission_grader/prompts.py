from __future__ import annotations

from typing import Any

PROMPT_VERSION = "9.0"

# version: 9.0
# Static, cached (cache_control: ephemeral) grading instructions. The per-question pauta
# block (build_pauta_block) is a SECOND cached block so the ~35 submissions of one
# question share it.
GRADING_SYSTEM = """\
You grade ONE handwritten student answer to a math question. You receive 1-3 photos of
the student's work, plus (in the system context) the official solution (pauta) and the
domain's error catalog. Return everything via the `transcribe_and_align` tool.

Do THREE things:
1. transcription: transcribe the student's steps as LaTeX. For each step set `idx`
   (0-based), `latex`, and `legible=false` when you cannot read it confidently. Give an
   overall `confidence` in [0,1] and the student's `final_answer` (null if none).
2. alignment: map each student step to a checkpoint of the official solution. Each
   `matches` entry has `student_step_idx`, the `solution_checkpoint_idx` it corresponds to
   (or null) and a `verdict` (OK | ERROR | SKIPPED). Set `path` to MAIN, ALT_<n> (an
   alternative path present in the pauta) or UNALIGNED.
3. provisional: `is_correct`, a `score_0_1`, and `first_error_step_idx` (the student step
   index of the first ERROR, or null).

Do NOT assign error-catalog tags — only transcribe, align and give the provisional
verdict; the definitive tag is decided downstream. Be faithful to what is written; never
solve the problem for the student.
"""

_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "idx": {"type": "integer", "minimum": 0},
        "latex": {"type": "string"},
        "legible": {"type": "boolean"},
    },
    "required": ["idx", "latex"],
}

_MATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "student_step_idx": {"type": "integer", "minimum": 0},
        "solution_checkpoint_idx": {"type": ["integer", "null"], "minimum": 0},
        "verdict": {"type": "string", "enum": ["OK", "ERROR", "SKIPPED"]},
    },
    "required": ["student_step_idx", "verdict"],
}

TRANSCRIBE_AND_ALIGN_TOOL: dict[str, Any] = {
    "name": "transcribe_and_align",
    "description": (
        "Transcribe the student's handwritten work, align it to the official solution "
        "and return a provisional verdict."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "transcription": {
                "type": "object",
                "properties": {
                    "steps": {"type": "array", "items": _STEP_SCHEMA},
                    "final_answer": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["steps", "confidence"],
            },
            "alignment": {
                "type": "object",
                "properties": {
                    "matches": {"type": "array", "items": _MATCH_SCHEMA},
                    "path": {"type": "string"},
                },
                "required": ["matches", "path"],
            },
            "provisional": {
                "type": "object",
                "properties": {
                    "is_correct": {"type": "boolean"},
                    "score_0_1": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "first_error_step_idx": {"type": ["integer", "null"], "minimum": 0},
                },
                "required": ["is_correct", "score_0_1"],
            },
        },
        "required": ["transcription", "alignment", "provisional"],
    },
}


def build_pauta_block(
        solution_steps_json: str,
        solution_final_answer: str,
        domain_catalog_text: str) -> str:
    """Per-question cached block (system, ephemeral): official solution + error catalog.
    The catalog extract anchors Haiku's 4096-token cacheable minimum (ADR v9 A8.1)."""
    return (
        "<official_solution>\n"
        f"{solution_steps_json}\n"
        f"final_answer: {solution_final_answer}\n"
        "</official_solution>\n"
        "<error_catalog>\n"
        f"{domain_catalog_text}\n"
        "</error_catalog>"
    )


def build_grade_user_text(grade_level: int, question_label: str | None) -> str:
    """Per-submission user instruction (not cached). No PII — only grade + label."""
    label = f" Question label: {question_label}." if question_label else ""
    return (
        f"Grade level: {grade_level}.{label} "
        "Transcribe, align and grade the attached photos via transcribe_and_align."
    )
