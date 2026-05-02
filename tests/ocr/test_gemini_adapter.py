from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from src.ocr.schemas import OcrProvider, OcrResult


def _build_gemini_response(latex_steps: list[str], confidence: float) -> MagicMock:
    payload = json.dumps(
        {
            "latex_steps": latex_steps,
            "overall_confidence": confidence,
            "final_answer": latex_steps[-1] if latex_steps else "",
            "topic_hint": "subtraction_borrow",
        }
    )
    mock = MagicMock()
    mock.text = payload
    return mock


def test_gemini_adapter_returns_valid_schema() -> None:
    with patch("google.genai.Client") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        mock_instance.models.generate_content.return_value = _build_gemini_response(
            latex_steps=["345", "345-178", "167"],
            confidence=0.92,
        )
        from src.ocr.gemini_adapter import GeminiAdapter

        adapter = GeminiAdapter()
        result = asyncio.run(adapter.extract(image_bytes=b"fake", trace_id="test"))

        assert isinstance(result, OcrResult)
        assert result.overall_confidence == 0.92
        assert result.provider == OcrProvider.GEMINI
        assert len(result.latex_steps) == 3


@pytest.mark.smoke
def test_gemini_live_smoke() -> None:
    """Smoke test: 1 real Gemini call. Runs only on push to main."""
    from src.ocr.gemini_adapter import GeminiAdapter

    adapter = GeminiAdapter()
    result = asyncio.run(adapter.extract(image_bytes=b"fake_image", trace_id="smoke"))
    assert isinstance(result, OcrResult)
    assert result.overall_confidence >= 0.0
