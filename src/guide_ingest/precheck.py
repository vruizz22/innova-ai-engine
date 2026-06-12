from __future__ import annotations

import json
from typing import cast

import structlog
from google import genai  # type: ignore[import-untyped]
from google.genai import types as genai_types  # type: ignore[import-untyped]

from src.guide_ingest.schemas import PdfKind, PrecheckResult
from src.shared.killswitch import ensure_not_paused
from src.shared.settings import get_settings

logger = structlog.get_logger()

_MODEL = "gemini-2.0-flash"

_PRECHECK_PROMPT = """\
You are triaging a Chilean K-12 math worksheet PDF before an expensive extraction step.
Inspect the document and return ONLY a JSON object (no markdown) with:
  - kind: "SCANNED" | "DIGITAL" | "MIXED"
  - content_pages: array of 0-based page indices that contain actual questions
  - quality: number 0..1 (legibility/usability for math extraction; <0.5 means re-scan)
  - notes: short actionable string when quality is low (e.g. "pages 3-5 blurred"), else ""
"""


def _parse(text: str, trace_id: str) -> PrecheckResult:
    try:
        raw = cast(dict[str, object], json.loads(text))
    except Exception:
        logger.warning("guide_precheck_parse_failed", trace_id=trace_id)
        return PrecheckResult(
            kind=PdfKind.MIXED,
            quality=0.0,
            notes="precheck parse failed")

    kind_value = str(raw.get("kind", "MIXED")).upper()
    kind = PdfKind(
        kind_value) if kind_value in PdfKind.__members__ else PdfKind.MIXED
    pages = [
        int(p)
        for p in cast(list[object], raw.get("content_pages") or [])
        if isinstance(p, (int, float))
    ]
    quality = max(0.0, min(1.0, float(cast(float, raw.get("quality") or 0.0))))
    notes_raw = raw.get("notes")
    notes = str(notes_raw) if notes_raw else None
    return PrecheckResult(
        kind=kind,
        content_pages=pages,
        quality=quality,
        notes=notes)


class GeminiPrecheck:
    """`PdfPrecheckPort` via Gemini 2.0 Flash — cheap kind/quality triage (ADR v9 A6.1)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = genai.Client(
            api_key=settings.gemini_api_key)  # type: ignore[attr-defined]
        self._paused_param = settings.ssm_guides_ingest_paused_param

    async def precheck(
            self,
            pdf_bytes: bytes,
            *,
            trace_id: str = "") -> PrecheckResult:
        ensure_not_paused(self._paused_param, trace_id=trace_id)
        response = await self._client.aio.models.generate_content(  # type: ignore[attr-defined]
            model=_MODEL,
            contents=[
                _PRECHECK_PROMPT,
                genai_types.Part.from_bytes(  # type: ignore[attr-defined]
                    data=pdf_bytes, mime_type="application/pdf"
                ),
            ],
        )
        result = _parse(response.text or "", trace_id)
        logger.info(
            "guide_precheck_done",
            kind=result.kind,
            quality=result.quality,
            content_pages=len(result.content_pages),
            trace_id=trace_id,
        )
        return result
