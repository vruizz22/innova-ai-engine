from __future__ import annotations

import io

import structlog

from src.guide_ingest.schemas import FigureBBox

logger = structlog.get_logger()

# ~144 dpi crops (2x zoom) — enough for figures without bloating S3. Integer scale
# matches pypdfium2's `render(scale: int)` signature; 2 and 2.0 render
# identically.
_RENDER_SCALE = 2


def bbox_to_pixels(bbox: FigureBBox, width_px: int, height_px: int) -> tuple[int, int, int, int]:
    """Normalized top-left [0,1] bbox -> integer pixel box (left, top, right, bottom),
    ordered and clamped to a non-empty region. Pure (unit-tested without pypdfium2)."""
    left = int(min(bbox.x0, bbox.x1) * width_px)
    right = int(max(bbox.x0, bbox.x1) * width_px)
    top = int(min(bbox.y0, bbox.y1) * height_px)
    bottom = int(max(bbox.y0, bbox.y1) * height_px)
    right = max(right, left + 1)
    bottom = max(bottom, top + 1)
    return (left, top, right, bottom)


class Pypdfium2Processor:
    """`PdfProcessorPort` via pypdfium2 (+ Pillow for crops). The native deps are imported
    lazily so the rest of the package imports/tests without pypdfium2 installed."""

    def page_count(self, pdf_bytes: bytes) -> int:
        import pypdfium2 as pdfium  # type: ignore

        pdf = pdfium.PdfDocument(pdf_bytes)
        try:
            return len(pdf)
        finally:
            pdf.close()

    def slice_pages(self, pdf_bytes: bytes, start: int, end: int) -> bytes:
        import pypdfium2 as pdfium  # type: ignore

        src = pdfium.PdfDocument(pdf_bytes)
        dst = pdfium.PdfDocument.new()
        try:
            dst.import_pages(src, pages=list(range(start, end)))
            buffer = io.BytesIO()
            dst.save(buffer)
            return buffer.getvalue()
        finally:
            dst.close()
            src.close()

    def crop_figure(self, pdf_bytes: bytes, bbox: FigureBBox) -> bytes:
        import pypdfium2 as pdfium  # type: ignore

        pdf = pdfium.PdfDocument(pdf_bytes)
        try:
            page = pdf[bbox.page]
            bitmap = page.render(scale=_RENDER_SCALE)
            image = bitmap.to_pil()
            box = bbox_to_pixels(bbox, image.width, image.height)
            crop = image.crop(box)
            out = io.BytesIO()
            crop.save(out, format="PNG")
            return out.getvalue()
        finally:
            pdf.close()
