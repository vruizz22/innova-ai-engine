from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

from src.ocr.schemas import OcrProvider, OcrResult


def _build_claude_response(
        latex_steps: list[str],
        confidence: float) -> MagicMock:
    payload = json.dumps({"latex_steps": latex_steps,
                          "overall_confidence": confidence,
                          "topic_hint": None})
    block = MagicMock()
    block.text = payload
    response = MagicMock()
    response.content = [block]
    return response


def test_claude_adapter_returns_valid_schema() -> None:
    with patch("src.ocr.claude_adapter.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _build_claude_response(
            latex_steps=["x+1=3", "x=2"], confidence=0.85
        )
        from src.ocr.claude_adapter import ClaudeAdapter

        adapter = ClaudeAdapter()
        result = asyncio.run(
            adapter.extract(
                image_bytes=b"fake",
                trace_id="test"))

        assert isinstance(result, OcrResult)
        assert result.provider == OcrProvider.CLAUDE
        assert result.overall_confidence == 0.85
        assert len(result.latex_steps) == 2
