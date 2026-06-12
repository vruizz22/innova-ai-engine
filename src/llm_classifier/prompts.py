from __future__ import annotations

from pydantic import BaseModel

# version: 1.0
SYSTEM_PROMPT = """\
You are an expert math education assessor specialized in detecting procedural errors \
in elementary school arithmetic (Chilean MINEDUC curriculum, 3rd-6th grade).

Your task: given a student's step-by-step solution to a math problem AND the canonical \
solution, identify the FIRST procedural error using a controlled vocabulary of error types.

You MUST use the `classify_errors` tool to return your classification. Never reply \
in plain text. If a step is correct or you cannot identify a known error, return error_type \
"UNCLASSIFIED" with reasoning.

You receive batches of up to 20 attempts at a time. Process each independently.\
"""

ERROR_TAXONOMY = """\
[ERROR TAXONOMY -- full reference. Use ONLY these error_type identifiers.]

SUBTRACTION_BORROW topic:
- BORROW_OMITTED_TENS: student subtracted in tens column without borrowing.
  Example: 53 - 26: writes "33" instead of 27.
- BORROW_OMITTED_HUNDREDS: same but in hundreds column.
- SUBTRAHEND_MINUEND_SWAPPED: student computed subtrahend - minuend instead of minuend - subtrahend.
- BORROW_FROM_ZERO_INCORRECT: borrow from a zero column performed incorrectly.
- STOP_BORROW_PROPAGATION: borrow stopped propagating mid-chain.
- DIGIT_TRANSPOSITION: correct digits, wrong order (e.g., 72 vs 27).
- COLUMN_MISALIGNMENT: vertical alignment wrong, leading to incorrect column subtractions.
- ARITHMETIC_FACT_ERROR: basic arithmetic fact wrong (off by <=2). Fallback rule.

ADDITION_CARRY topic:
- CARRY_OMITTED: did not carry to next column.
- CARRY_ADDED_TO_WRONG_COLUMN: carry placed in wrong column.

FRACTIONS_ADDSUB_SAME_DENOM topic:
- SUM_NUMERATORS_AND_DENOMINATORS: added/subtracted both numerator and denominator.
- IMPROPER_FRACTION_NOT_REDUCED: result correct but not simplified.
- INVERTED_FRACTION: numerator/denominator accidentally swapped.
- WHOLE_NUMBER_LOST: lost integer part in mixed-number addition.

MULT_SINGLE_DIGIT topic:
- TABLE_RECALL_ERROR: multiplication table fact incorrect.
- CARRY_OMITTED_MULT: forgot to carry in multi-digit multiplication.
- ZERO_TIMES_X_NONZERO: wrote non-zero result for 0 x n.

DIVISION_LONG topic:
- DIVISOR_DIVIDEND_SWAPPED: confused which is divisor vs dividend.
- REMAINDER_GREATER_THAN_DIVISOR: remainder exceeds divisor.
- BRING_DOWN_OMITTED: forgot to bring down the next digit.

FRACTIONS_ADDSUB_DIFF_DENOM topic:
- COMMON_DENOMINATOR_MISSED: added without finding common denominator.
- WRONG_LCM: found wrong LCM for common denominator.

Special values:
- CORRECT: student answer matches canonical solution.
- UNCLASSIFIED: no known error pattern detected.
"""

FEW_SHOTS = """\
[FEW-SHOTS]

Example 1:
Problem: 345 - 178 | Canonical: 167
Student steps: [units: "5-8=3", tens: "4-7=??"]  Student answer: "233"
-> classify_errors: {attempt_id: "...", error_type: "BORROW_OMITTED_TENS",
   evidence: "Student wrote 5-8=3 (no borrow) instead of 15-8 with borrow from tens",
   confidence: 0.95}

Example 2:
Problem: 53 - 26 | Canonical: 27  Student answer: "27"
-> classify_errors: {attempt_id: "...", error_type: "CORRECT",
   evidence: "Correct answer", confidence: 1.0}

Example 3:
Problem: 100 - 47 | Student steps: incoherent  Student answer: "0"
-> classify_errors: {attempt_id: "...", error_type: "UNCLASSIFIED",
   evidence: "Student appears to have given up; no procedural pattern detected",
   confidence: 0.0}
"""

CACHED_BLOCK = SYSTEM_PROMPT + "\n\n" + ERROR_TAXONOMY + "\n\n" + FEW_SHOTS


# =====================================================================
# v8 — by-domain prompts (ADR A4.1 / ADR-114)
#
# One specialized, cacheable system prompt per domain. The error catalog itself is
# NOT hardcoded here: it is injected at runtime from the DB (`catalog.taxonomy_text`)
# so the prompt always reflects the ACTIVE error_tags. We keep a registry (instead of
# 18 near-identical files) because the only per-domain difference is the specialization
# header — the catalog is data, not code. Caching still happens per domain because the
# assembled system block is unique per domain_code + catalog_hash.
# =====================================================================

# version: 2.0


class DomainPromptSpec(BaseModel):
    code: str
    title: str
    grade_range: str


# Keyed by Domain.code (matches the 17 domains seeded in the backend).
DOMAIN_SPECS: dict[str, DomainPromptSpec] = {
    "ARITH": DomainPromptSpec(
        code="ARITH", title="Arithmetic with natural numbers", grade_range="G1-G6"
    ),
    "INT": DomainPromptSpec(
        code="INT", title="Integers (signed numbers)", grade_range="G7-G8"
    ),
    "FRACT": DomainPromptSpec(code="FRACT", title="Fractions", grade_range="G4-G8"),
    "DEC": DomainPromptSpec(code="DEC", title="Decimal numbers", grade_range="G5-G8"),
    "RATIO": DomainPromptSpec(
        code="RATIO",
        title="Ratios, proportions and percentages",
        grade_range="G6-G8",
    ),
    "ALGEBRA": DomainPromptSpec(
        code="ALGEBRA",
        title="Algebra (expressions, equations, systems)",
        grade_range="G7-G12",
    ),
    "POW": DomainPromptSpec(
        code="POW", title="Powers and roots", grade_range="G8-G10"
    ),
    "FUNC": DomainPromptSpec(code="FUNC", title="Functions", grade_range="G8-G12"),
    "GEOM": DomainPromptSpec(
        code="GEOM", title="Plane geometry", grade_range="G3-G10"
    ),
    "GEOM3D": DomainPromptSpec(
        code="GEOM3D", title="3D geometry, area and volume", grade_range="G5-G12"
    ),
    "TRIG": DomainPromptSpec(
        code="TRIG", title="Trigonometry", grade_range="G10-G12"
    ),
    "STAT": DomainPromptSpec(
        code="STAT", title="Statistics", grade_range="G4-G12"
    ),
    "DATA": DomainPromptSpec(
        code="DATA", title="Data handling and probability", grade_range="G1-G8"
    ),
    "LOG": DomainPromptSpec(
        code="LOG", title="Logic and sets", grade_range="G7-G12"
    ),
    "SEQ": DomainPromptSpec(
        code="SEQ", title="Sequences and patterns", grade_range="G7-G12"
    ),
    "COORD": DomainPromptSpec(
        code="COORD", title="Coordinate geometry", grade_range="G6-G12"
    ),
    "TRANSV": DomainPromptSpec(
        code="TRANSV",
        title="Transversal (cross-cutting) procedural errors",
        grade_range="G1-G12",
    ),
}

_DOMAIN_PROMPT_TEMPLATE = """\
You are an expert math education assessor specialized in {title} \
({grade_range}, Chilean MINEDUC curriculum).

Your task: given a student's step-by-step solution AND the canonical solution, \
identify the FIRST procedural error using ONLY the controlled error catalog below.

You MUST use the `classify_errors` tool to return your classification. Never reply \
in plain text. Process each attempt in the batch independently.

Special values:
- CORRECT: the student's answer matches the canonical solution.
- UNCLASSIFIED: no catalog error fits (use it rather than forcing a wrong code).
- TRANSVERSAL_LIKELY: the error is real but cross-cutting (not specific to this \
domain, e.g. careless transcription, sign handling, units) -- defer to a second pass.

{taxonomy}\
"""


def build_domain_system_prompt(
        spec: DomainPromptSpec,
        taxonomy_text: str) -> str:
    """Assemble the cacheable system block for one domain with its ACTIVE catalog."""
    return _DOMAIN_PROMPT_TEMPLATE.format(
        title=spec.title,
        grade_range=spec.grade_range,
        taxonomy=taxonomy_text,
    )
