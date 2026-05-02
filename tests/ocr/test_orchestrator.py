from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from src.ocr.schemas import OcrProvider, OcrResult


def test_orchestrator_uses_gemini_when_high_confidence() -> None:
    from src.ocr.claude_adapter import ClaudeAdapter
    from src.ocr.gemini_adapter import GeminiAdapter
    from src.ocr.orchestrator import OcrOrchestrator

    high = OcrResult(
        latex_steps=["x=3"],
        overall_confidence=0.9,
        provider=OcrProvider.GEMINI)

    with patch.object(GeminiAdapter, "extract", new=AsyncMock(return_value=high)):
        with patch.object(ClaudeAdapter, "extract", new=AsyncMock()) as mock_claude:
            orch = OcrOrchestrator()
            result = asyncio.run(orch.extract(image_bytes=b"fake"))
            mock_claude.assert_not_called()
            assert result.provider == OcrProvider.GEMINI


def test_orchestrator_escalates_to_claude_on_low_confidence() -> None:
    from src.ocr.claude_adapter import ClaudeAdapter
    from src.ocr.gemini_adapter import GeminiAdapter
    from src.ocr.orchestrator import OcrOrchestrator

    low = OcrResult(
        latex_steps=[],
        overall_confidence=0.5,
        provider=OcrProvider.GEMINI)
    high = OcrResult(
        latex_steps=[
            "x+2=5",
            "x=3"],
        overall_confidence=0.88,
        provider=OcrProvider.CLAUDE)

    with patch.object(GeminiAdapter, "extract", new=AsyncMock(return_value=low)):
        with patch.object(
            ClaudeAdapter, "extract", new=AsyncMock(return_value=high)
        ) as mock_claude:
            orch = OcrOrchestrator()
            result = asyncio.run(orch.extract(image_bytes=b"fake"))
            mock_claude.assert_called_once()
            assert result.provider == OcrProvider.CLAUDE
            assert result.overall_confidence == 0.88


def test_orchestrator_keeps_gemini_if_claude_worse() -> None:
    from src.ocr.claude_adapter import ClaudeAdapter
    from src.ocr.gemini_adapter import GeminiAdapter
    from src.ocr.orchestrator import OcrOrchestrator

    gemini_r = OcrResult(
        latex_steps=["x=1"],
        overall_confidence=0.4,
        provider=OcrProvider.GEMINI)
    claude_r = OcrResult(
        latex_steps=[],
        overall_confidence=0.3,
        provider=OcrProvider.CLAUDE)

    with patch.object(GeminiAdapter, "extract", new=AsyncMock(return_value=gemini_r)):
        with patch.object(ClaudeAdapter, "extract", new=AsyncMock(return_value=claude_r)):
            orch = OcrOrchestrator()
            result = asyncio.run(orch.extract(image_bytes=b"fake"))
            assert result.provider == OcrProvider.GEMINI
