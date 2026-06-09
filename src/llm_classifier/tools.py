from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.llm_classifier.catalog import SPECIAL_ERROR_TYPES

CLASSIFY_TOOL: dict[str, Any] = {
    "name": "classify_errors",
    "description": "Classify procedural math errors for a batch of student attempts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "minItems": 1,
                "maxItems": 25,
                "items": {
                    "type": "object",
                    "properties": {
                        "attempt_id": {"type": "string"},
                        "error_type": {
                            "type": "string",
                            "enum": [
                                "BORROW_OMITTED_TENS",
                                "BORROW_OMITTED_HUNDREDS",
                                "SUBTRAHEND_MINUEND_SWAPPED",
                                "BORROW_FROM_ZERO_INCORRECT",
                                "STOP_BORROW_PROPAGATION",
                                "DIGIT_TRANSPOSITION",
                                "COLUMN_MISALIGNMENT",
                                "ARITHMETIC_FACT_ERROR",
                                "CARRY_OMITTED",
                                "CARRY_ADDED_TO_WRONG_COLUMN",
                                "SUM_NUMERATORS_AND_DENOMINATORS",
                                "IMPROPER_FRACTION_NOT_REDUCED",
                                "INVERTED_FRACTION",
                                "WHOLE_NUMBER_LOST",
                                "TABLE_RECALL_ERROR",
                                "CARRY_OMITTED_MULT",
                                "ZERO_TIMES_X_NONZERO",
                                "DIVISOR_DIVIDEND_SWAPPED",
                                "REMAINDER_GREATER_THAN_DIVISOR",
                                "BRING_DOWN_OMITTED",
                                "COMMON_DENOMINATOR_MISSED",
                                "WRONG_LCM",
                                "CORRECT",
                                "UNCLASSIFIED",
                            ],
                        },
                        "evidence": {"type": "string", "maxLength": 300},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    },
                    "required": ["attempt_id", "error_type", "evidence", "confidence"],
                },
            }
        },
        "required": ["classifications"],
    },
}


def build_classify_tool(error_codes: Sequence[str]) -> dict[str, Any]:
    """v8 — build a `classify_errors` tool whose error_type enum is the ACTIVE
    catalog of a single domain plus the special values (CORRECT / UNCLASSIFIED /
    TRANSVERSAL_LIKELY). Constraining the enum keeps the model on real ErrorTag codes
    so the FK resolves on the backend write."""
    enum_values = [*error_codes, *SPECIAL_ERROR_TYPES]
    return {
        "name": "classify_errors",
        "description": "Classify procedural math errors for a batch of student attempts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "classifications": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 25,
                    "items": {
                        "type": "object",
                        "properties": {
                            "attempt_id": {
                                "type": "string"},
                            "error_type": {
                                "type": "string",
                                "enum": enum_values},
                            "evidence": {
                                "type": "string",
                                "maxLength": 300},
                            "confidence": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                            },
                        },
                        "required": [
                            "attempt_id",
                            "error_type",
                            "evidence",
                            "confidence",
                        ],
                    },
                }},
            "required": ["classifications"],
        },
    }
