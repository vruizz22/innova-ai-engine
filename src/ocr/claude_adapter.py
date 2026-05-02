from __future__ import annotations

import base64
import json
from typing import cast

import structlog
from anthropic import Anthropic

from src.shared.settings import get_settings
from src.ocr.schemas import OcrProvider, OcrResult

logger = structlog.get_logger()


class ClaudeAdapter:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)

    async def extract(
            self,
            image_bytes: bytes,
            trace_id: str = "") -> OcrResult:
        image_b64 = base64.b64encode(image_bytes).decode()
        response = self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Extract student math steps from this image. "
                                "Return JSON: "
                                '{"latex_steps": [], "overall_confidence": 0.0, "topic_hint": null}'
                            ),
                        },
                    ],
                }
            ],
        )
        try:
            block = response.content[0]
            text = cast(str, block.text)  # type: ignore[attr-defined]
            start = text.find("{")
            end = text.rfind("}") + 1
            parsed: dict[str, object] = json.loads(text[start:end])
        except Exception:
            logger.warning("claude_ocr_parse_failed", trace_id=trace_id)
            return OcrResult(
                latex_steps=[],
                overall_confidence=0.0,
                provider=OcrProvider.CLAUDE)

        return OcrResult(
            latex_steps=[
                str(s) for s in cast(
                    list[object],
                    parsed.get("latex_steps") or [])],
            overall_confidence=float(
                cast(
                    float,
                    parsed.get("overall_confidence") or 0.0)),
            provider=OcrProvider.CLAUDE,
            topic_hint=str(
                parsed["topic_hint"]) if parsed.get("topic_hint") else None,
        )
