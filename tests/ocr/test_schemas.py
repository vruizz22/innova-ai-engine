from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.ocr.schemas import OcrProvider, OcrResult


def test_ocr_result_valid() -> None:
    r = OcrResult(
        latex_steps=[
            "x+1=3",
            "x=2"],
        overall_confidence=0.9,
        provider=OcrProvider.GEMINI)
    assert r.provider == OcrProvider.GEMINI
    assert len(r.latex_steps) == 2


def test_ocr_result_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        OcrResult(
            latex_steps=[],
            overall_confidence=1.5,
            provider=OcrProvider.GEMINI)


def test_ocr_provider_enum_values() -> None:
    assert OcrProvider.GEMINI == "GEMINI"
    assert OcrProvider.CLAUDE == "CLAUDE"
