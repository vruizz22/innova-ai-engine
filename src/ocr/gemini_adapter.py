from __future__ import annotations

import json
from typing import cast

import structlog
from google import genai  # type: ignore[import-untyped]
from google.genai import types as genai_types  # type: ignore[import-untyped]

from src.ocr.schemas import OcrProvider, OcrResult
from src.shared.settings import get_settings

logger = structlog.get_logger()

OCR_PROMPT = """\
You are an expert transcriber of Chilean elementary school (grades 3-6) handwritten math.
Extract the student's step-by-step solution from this image.
Return a JSON object with fields:
  - latex_steps: list of strings representing each step
  - final_answer: string
  - overall_confidence: number 0-1
  - topic_hint: string or null (e.g. "subtraction_borrow")
"""


class GeminiAdapter:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = genai.Client(api_key=settings.gemini_api_key)  # type: ignore[attr-defined]
        self._model = settings.gemini_model

    async def extract(self, image_bytes: bytes, trace_id: str = "") -> OcrResult:
        # Async SDK call (`.aio`): no sync HTTP inside an async port (CLAUDE.md §13).
        response = await self._client.aio.models.generate_content(  # type: ignore[attr-defined]
            model=self._model,
            contents=[
                OCR_PROMPT,
                genai_types.Part.from_bytes(  # type: ignore[attr-defined]
                    data=image_bytes, mime_type="image/jpeg"
                ),
            ],
        )
        try:
            parsed: dict[str, object] = json.loads(response.text or "")
        except Exception:
            logger.warning("gemini_ocr_parse_failed", trace_id=trace_id)
            return OcrResult(latex_steps=[], overall_confidence=0.0, provider=OcrProvider.GEMINI)

        return OcrResult(
            latex_steps=[str(s) for s in cast(list[object], parsed.get("latex_steps") or [])],
            overall_confidence=float(cast(float, parsed.get("overall_confidence") or 0.0)),
            provider=OcrProvider.GEMINI,
            topic_hint=str(parsed["topic_hint"]) if parsed.get("topic_hint") else None,
            cost_estimated_usd=0.0,
        )
