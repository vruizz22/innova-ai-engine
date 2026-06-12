from __future__ import annotations

from typing import Any

# version: 9.0
# Cached (cache_control: ephemeral) system prompt for the Sonnet guide extractor.
# Keep this STATIC so the prompt-cache key is stable; per-guide data (grade, chunk)
# travels in the user turn.
EXTRACT_GUIDE_SYSTEM = """\
You extract structured questions from a Chilean K-12 math worksheet ("guía") PDF.

You receive ONE PDF chunk (up to 20 pages). Identify every distinct question/exercise
and return them via the `extract_guide` tool. Rules:

- Preserve math exactly as LaTeX in `statement_latex`; put a plain-language version in
  `statement_text` (no LaTeX commands, for search/topic classification).
- `label` = the worksheet's own numbering ("1", "3.a", "II.2") or null if unlabeled.
- If the PDF includes the answer or a worked solution, fill `provided_answer` and/or
  `provided_solution_latex`. Otherwise leave them null — never invent them.
- For each figure/diagram/plot belonging to a question, add a `figure_bboxes` entry with
  the 0-based `page` index WITHIN THIS CHUNK and normalized [0,1] coordinates
  (top-left origin): x0,y0 = top-left corner, x1,y1 = bottom-right corner.
- Set `continues_previous=true` ONLY on the first question of the chunk when it is the
  tail of a question that started before this chunk (split by the page boundary).
- Ignore page headers/footers, instructions, and decorative content. Do not merge
  distinct questions; do not split one question into several.
"""

_QUESTION_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {"type": ["string", "null"]},
        "statement_latex": {"type": "string"},
        "statement_text": {"type": "string"},
        "provided_answer": {"type": ["string", "null"]},
        "provided_solution_latex": {"type": ["string", "null"]},
        "figure_bboxes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "minimum": 0},
                    "x0": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "y0": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "x1": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "y1": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["page", "x0", "y0", "x1", "y1"],
            },
        },
        "continues_previous": {"type": "boolean"},
    },
    "required": ["statement_latex", "statement_text"],
}

EXTRACT_GUIDE_TOOL: dict[str, Any] = {
    "name": "extract_guide",
    "description": "Return every question found in this guide PDF chunk.",
    "input_schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": _QUESTION_ITEM_SCHEMA,
            }
        },
        "required": ["questions"],
    },
}


def build_extract_user_text(grade_level: int, page_count: int) -> str:
    """Per-chunk user instruction (not cached)."""
    return (
        f"This chunk has {page_count} page(s) from a grade-{grade_level} math guide. "
        "Extract all questions via the extract_guide tool."
    )
