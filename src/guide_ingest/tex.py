from __future__ import annotations

import posixpath

from src.guide_ingest.schemas import MergedQuestion

_PREAMBLE = r"""\documentclass[12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[spanish]{babel}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{enumitem}
"""


def _question_block(question: MergedQuestion) -> str:
    """Render one question as an `enumerate` item, inlining any cropped figures by their
    S3 key basename (figures are uploaded alongside the .tex under guides/{id}/figures/)."""
    head = f"\\item[{question.label}.] " if question.label else "\\item "
    lines = [f"{head}{question.statement_latex}"]
    for key in question.figure_keys:
        name = posixpath.basename(key)
        graphic = f"\\\\\\includegraphics[width=0.6\\textwidth]{{figures/{name}}}"
        lines.append(f"  {graphic}")
    if question.provided_answer:
        lines.append(f"  \\\\\\textbf{{Respuesta:}} {question.provided_answer}")
    return "\n".join(lines)


def render_guide_tex(guide_id: str, questions: list[MergedQuestion]) -> str:
    """Render the full guide as a self-contained .tex document (ADR-117). Figure
    `\\includegraphics` paths are relative to the guide's S3 prefix."""
    body = "\n\n".join(_question_block(q) for q in questions)
    return (
        f"{_PREAMBLE}\n"
        f"% guide_id: {guide_id}\n"
        f"\\begin{{document}}\n\n"
        f"\\begin{{enumerate}}[leftmargin=*]\n"
        f"{body}\n"
        f"\\end{{enumerate}}\n\n"
        f"\\end{{document}}\n"
    )
