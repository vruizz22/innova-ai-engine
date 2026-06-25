from __future__ import annotations

import re

from src.solution_gen.schemas import GeneratedSolution


def _strip_latex(text: str) -> str:
    """Remove common LaTeX wrappers and normalise for comparison."""
    text = text.strip()
    # unwrap $…$  or \(…\)
    text = re.sub(r"^\$(.+)\$$", r"\1", text)
    text = re.sub(r"^\\\((.+)\\\)$", r"\1", text)
    # strip \frac{a}{b} → a/b (for numeric comparison)
    text = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"\1/\2", text)
    # strip remaining LaTeX commands (spaces/braces)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = re.sub(r"[{}]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _try_float(text: str) -> float | None:
    """Try to evaluate text as a float (handles simple fractions a/b)."""
    try:
        return float(text)
    except ValueError:
        pass
    m = re.match(r"^(-?\d+)\s*/\s*(-?\d+)$", text)
    if m:
        num, den = int(m.group(1)), int(m.group(2))
        if den != 0:
            return num / den
    return None


def answers_match(derived: str, student: str, *, tol: float = 1e-6) -> bool:
    """Return True when student's answer matches the LLM-derived canonical answer.

    Checks:
    1. Exact string match after LaTeX stripping + lowercase.
    2. Numeric match within tolerance for decimal/fraction answers.
    """
    d = _strip_latex(derived)
    s = _strip_latex(student)
    if d == s:
        return True
    # try numeric comparison
    df = _try_float(d)
    sf = _try_float(s)
    if df is not None and sf is not None:
        return abs(df - sf) <= tol
    # variable equations: "x=2" vs "x = 2"
    d_nospace = re.sub(r"\s", "", d)
    s_nospace = re.sub(r"\s", "", s)
    return d_nospace == s_nospace


def pick_error_tag(gen: GeneratedSolution, allowed: set[str]) -> str | None:
    """Return the first allowed expected_error_tag from the solution steps,
    or None when none can be found (triggers UNKNOWN_ERROR fallback)."""
    for step in gen.steps:
        for tag in step.expected_error_tags:
            if tag in allowed:
                return tag
    return None
