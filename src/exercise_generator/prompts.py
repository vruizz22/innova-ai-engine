from __future__ import annotations

GENERATE_SYSTEM = """You are an expert Chilean mathematics teacher creating \
exercises for K-12 students.

Your exercises must:
- Use LaTeX notation for all math expressions (e.g. \\frac{3}{4}, 12 \\times 5)
- Be appropriate for Chilean curriculo nacional (MINEDUC)
- Target specific mathematical error patterns to provide corrective practice
- Be solvable in 3-7 steps maximum
- Never contain student names, photos, or any PII
- Be original — do not copy verbatim from textbooks

IRT parameters guidance:
- irt_a (discrimination): 0.5=easy to discriminate, 3.0=hard to discriminate; default 1.0
- irt_b (difficulty): -3=very easy, 0=average, 3=very hard; default 0.0
  Match irt_b to grade level: grade 3-4 → -0.5 to 0.5, grade 5-6 → 0.0 to 1.0,
  grade 7-8 → 0.5 to 1.5, grade 9-12 → 1.0 to 2.0"""

GENERATE_EXERCISES_TOOL: dict[str, object] = {
    "name": "generate_exercises",
    "description": "Output a list of structured math exercises targeting specific error patterns.",
    "input_schema": {
        "type": "object",
        "properties": {
            "exercises": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "problem_latex": {
                            "type": "string",
                            "description": (
                                "The exercise problem in LaTeX (no surrounding $). "
                                "Example: 'Resuelve: \\\\frac{2}{3} + \\\\frac{1}{4}'"
                            ),
                        },
                        "correct_answer_latex": {
                            "type": "string",
                            "description": "The correct final answer in LaTeX.",
                        },
                        "solution_steps_latex": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Step-by-step solution, each step as a LaTeX string.",
                        },
                        "irt_a": {
                            "type": "number",
                            "description": "IRT discrimination parameter (0.5 to 3.0).",
                        },
                        "irt_b": {
                            "type": "number",
                            "description": "IRT difficulty parameter (-3.0 to 3.0).",
                        },
                        "target_error_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Error codes this exercise specifically targets.",
                        },
                    },
                    "required": [
                        "problem_latex",
                        "correct_answer_latex",
                        "irt_a",
                        "irt_b",
                        "target_error_codes",
                    ],
                },
            }
        },
        "required": ["exercises"],
    },
}


def build_generate_user_text(
    *,
    subdomain_code: str,
    subdomain_description: str,
    grade_level: int,
    target_error_codes: list[str],
    error_descriptions: list[str],
    count: int,
) -> str:
    error_lines = "\n".join(
        f"- {code}: {desc}"
        for code, desc in zip(target_error_codes, error_descriptions, strict=False)
    )
    return (
        f"Subdomain: {subdomain_code}\n"
        f"Description: {subdomain_description}\n"
        f"Grade level: {grade_level}° (Chile)\n\n"
        f"Target error patterns:\n{error_lines}\n\n"
        f"Generate exactly {count} original exercise(s). Each must target at least one "
        f"of the listed error patterns and be solvable at grade {grade_level} level."
    )
