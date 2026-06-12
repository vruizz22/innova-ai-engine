from __future__ import annotations

from src.guide_ingest.pdf_processor import bbox_to_pixels
from src.guide_ingest.schemas import FigureBBox


def test_bbox_to_pixels_scales_normalized_coords() -> None:
    bbox = FigureBBox(page=0, x0=0.1, y0=0.2, x1=0.5, y1=0.6)
    assert bbox_to_pixels(bbox, 1000, 1000) == (100, 200, 500, 600)


def test_bbox_to_pixels_orders_and_guarantees_nonempty() -> None:
    bbox = FigureBBox(page=0, x0=0.5, y0=0.5, x1=0.5, y1=0.5)
    left, top, right, bottom = bbox_to_pixels(bbox, 100, 100)
    assert right > left
    assert bottom > top
