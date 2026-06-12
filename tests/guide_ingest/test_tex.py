from __future__ import annotations

from src.guide_ingest.schemas import MergedQuestion
from src.guide_ingest.tex import render_guide_tex


def test_renders_questions_figures_and_answer() -> None:
    questions = [
        MergedQuestion(
            sequence=1,
            label="1",
            statement_latex="$x+1$",
            statement_text="x plus 1",
            figure_keys=["guides/g1/figures/q1_0.png"],
            provided_answer="2",
        )
    ]
    tex = render_guide_tex("g1", questions)
    assert "\\documentclass" in tex
    assert "$x+1$" in tex
    assert "q1_0.png" in tex
    assert "guide_id: g1" in tex
    assert "Respuesta:" in tex
    assert tex.rstrip().endswith("\\end{document}")
