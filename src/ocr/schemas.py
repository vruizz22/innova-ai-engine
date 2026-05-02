from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class OcrProvider(StrEnum):
    GEMINI = "GEMINI"
    CLAUDE = "CLAUDE"


class OcrResult(BaseModel):
    latex_steps: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    provider: OcrProvider
    topic_hint: str | None = None
    cost_estimated_usd: float = 0.0
