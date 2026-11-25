"""Serialize verified page GT in the heocr_document.v1 layout contract."""
from __future__ import annotations

import math


def _boxes(items):
    return [min(box[0] for box in items), min(box[1] for box in items),
            max(box[2] for box in items), max(box[3] for box in items)]


def image_record(page, projections, *, image_sha256, image_bytes, image_size, dpi, image_format,
                 producer_version, producer, capture, native_pdf_sha256):
    """Use verified source order and transformed line polygons to build image-frame GT.

    Polygon vertices are image pixels from the top left. The contract's boxes are
    top-left points at the displayed image's DPI, including for phone photos.
    """
    width, height = image_size
    if dpi <= 0 or width <= 0 or height <= 0:
        raise ValueError("Invalid image size or DPI")
    points_per_pixel = 72 / dpi

    def line_record(line, polygon):
        if len(polygon) < 4 or any(
            not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= width and 0 <= y <= height)
            for x, y in polygon
        ):
            raise ValueError("Projected line polygon leaves the image")
        xs, ys = zip(*polygon, strict=True)
        box = [min(xs), min(ys), max(xs), max(ys)]
        if box[0] >= box[2] or box[1] >= box[3]:
            raise ValueError("Projected line polygon is degenerate")
        return {"text": line["text"], "direction": "rtl", "polygon_px": polygon,
                "bbox": [round(value * points_per_pixel, 6) for value in box]}

    blocks = []
    expected = set()
    for i, region in enumerate(page["regions"]):
        lines = []
        for j, line in enumerate(region["lines"]):
            token = f"b{i}-l{j}"
            expected.add(token)
            lines.append(line_record(line, projections[token]))
        block = {
            **{key: region[key] for key in ("kind", "role", "text", "half", "level", "label", "note_id", "note_refs")
               if key in region},
            "id": f"b{i}", "page": 0, "direction": "rtl",
            "source": "text_layer", "tool": "pdfium", "lines": lines,
            "bbox": _boxes([line["bbox"] for line in lines]),
            "checks": {"source_block": region["source_id"]}, "repairs": [], "flags": [],
        }
        blocks.append(block)
    if set(projections) != expected:
        raise ValueError("Projected line IDs differ from the verified page")
    return {
        "schema": "heocr_document.v1",
        "producer": {"name": "heocr", "version": "synthetic-layout-ground-truth.v1",
                     "components": {producer: producer_version}},
        "document": {"sha256": image_sha256, "bytes": image_bytes, "format": image_format,
                     "format_evidence": "synthetic capture", "page_count": 1},
        "options": {"repairs": False, "ocr": False, "synthetic_calibration": True},
        "pages": [{
            "index": 0, "width": width * points_per_pixel, "height": height * points_per_pixel,
            "class": "T5", "route": "ground_truth", "coverage": {"status": "exact"},
            "signals": {"pixels": [width, height], "dpi": dpi, "capture": capture,
                        "native_pdf_sha256": native_pdf_sha256, "order": "blocks array"},
            "flags": [],
        }],
        "blocks": blocks,
        "unread": [],
        "flags": ["synthetic_layout_ground_truth"],
    }
