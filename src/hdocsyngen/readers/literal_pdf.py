"""Independent readers for a literal native PDF audit.

PDFMiner may use ActualText for its secondary readback. The glyph witness always
comes from MuPDF's painted text trace, which bypasses ActualText.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PaintedGlyph:
    text: str
    glyph_id: int
    origin: tuple[float, float]
    face: str


def painted_pages(path: Path) -> tuple[dict, list[list[PaintedGlyph]]]:
    import pymupdf

    with pymupdf.open(path) as doc:
        pages = []
        for page in doc:
            if page.rotation or page.cropbox != page.mediabox:
                raise ValueError("Literal readback requires an unrotated, uncropped PDF page")
            height = page.rect.height
            pages.append([
                PaintedGlyph(chr(code), gid, (origin[0], height - origin[1]), span["font"].split("+", 1)[-1])
                for span in page.get_texttrace() if span["type"] in (0, 1) and span["opacity"] > 0
                for code, gid, origin, _ in span["chars"]
                if 0 <= code <= 0x10FFFF and not chr(code).isspace()
            ])
        return doc.metadata, pages


def pdfminer_pages(path: Path) -> list[str]:
    from pdfminer.converter import PDFPageAggregator
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdftypes import resolve1
    from pdfminer.utils import decode_text

    class LiteralDevice(PDFPageAggregator):
        def __init__(self, resources):
            super().__init__(resources, laparams=None)
            self.marked = []
            self.text = []

        def begin_tag(self, tag, props=None):
            values = resolve1(props)
            actual = resolve1(values.get("ActualText")) if isinstance(values, dict) else None
            if isinstance(actual, bytes) and not any(self.marked):
                self.text.append(decode_text(actual))
            self.marked.append(isinstance(actual, bytes))

        def end_tag(self):
            if self.marked:
                self.marked.pop()

        def render_char(self, *args, **kwargs):
            advance = super().render_char(*args, **kwargs)
            if not any(self.marked):
                self.text.append(self.cur_item._objs[-1].get_text())
            return advance

    resources = PDFResourceManager()
    device = LiteralDevice(resources)
    interpreter = PDFPageInterpreter(resources, device)
    pages = []
    with path.open("rb") as stream:
        for page in PDFPage.get_pages(stream):
            device.marked.clear()
            device.text.clear()
            interpreter.process_page(page)
            pages.append("".join(device.text))
    return pages


def position_index(painted: list[PaintedGlyph]) -> dict[tuple[int, int], list[PaintedGlyph]]:
    """Index physical glyph origins in one-point bins."""
    index = defaultdict(list)
    for glyph in painted:
        x, y = glyph.origin
        index[int(x), int(y)].append(glyph)
    return index


def matching_glyph(index, origin, tolerance: float = 0.45) -> PaintedGlyph | None:
    """Return a unique physical witness within the PH1 position tolerance."""
    x, y = origin
    matches = {
        glyph for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        for glyph in index.get((int(x) + dx, int(y) + dy), ())
        if abs(glyph.origin[0] - x) <= tolerance and abs(glyph.origin[1] - y) <= tolerance
    }
    return matches.pop() if len(matches) == 1 else None
