"""Text-layer faults on producer PDFs (design note: F9 visual order, F5 split runs, F1 hidden OCR layers, missing
"." glyphs). The page looks the same; only its text layer changes, so the gold is unchanged.

How a faulted page is built:

1. The producer page's text is turned into outlines (Ghostscript ``-dNoOutputFonts``): it still renders, but no
   longer extracts. For ``hidden_ocr`` the page is instead rasterised (an image-only page, as a scan is).
2. An invisible text layer (render mode 3) is written over it from the producer's own characters and positions,
   with the faults applied, using an open Hebrew font the caller names.
3. The two are merged page by page.

The transforms on the extracted lines (``visual_order``, ``split_runs``, ``drop_dots``, ``offset``) are pure Python;
the PDF steps need the ``faults`` extra and Ghostscript.

    python -m hdocsyngen.layer_faults IN.pdf OUT.pdf --font FONT.ttf --faults visual_order,split_runs --seed 7
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

FAULTS = ("visual_order", "split_runs", "drop_dots", "hidden_ocr")
SPLIT_GAP = 0.35  # share of the font size: a gap this wide inside a word makes extractors break it


def _rtl(ch: str) -> bool:
    return "֐" <= ch <= "׿" or "יִ" <= ch <= "ﭏ"


@dataclass
class Char:
    text: str
    x0: float
    y0: float  # PDF frame (origin bottom left)
    x1: float
    y1: float
    k: int = 0          # the producer's order: the layer is written in it
    shift: float = 0.0  # extra x offset in the layer (a split gap), in reading direction


@dataclass
class Line:
    chars: list[Char]  # in the producer's order

    @property
    def size(self) -> float:
        heights = sorted(c.y1 - c.y0 for c in self.chars) or [10.0]
        return max(heights[len(heights) // 2], 1.0)


def lines_from_chars(chars: list[Char]) -> list[Line]:
    """Characters grouped into lines by vertical centre, each line in the producer's own order (a correct producer
    stores logical order; the faults change it from there)."""
    out: list[list[tuple[int, Char]]] = []
    for k, c in sorted(enumerate(chars), key=lambda kc: -(kc[1].y0 + kc[1].y1) / 2):
        cy = (c.y0 + c.y1) / 2
        if out and abs(cy - sum((d.y0 + d.y1) / 2 for _, d in out[-1]) / len(out[-1])) < 0.5 * max(c.y1 - c.y0, 1.0):
            out[-1].append((k, c))
        else:
            out.append([(k, c)])
    for k, c in enumerate(chars):
        c.k = k
    return [Line([c for _, c in sorted(group, key=lambda kc: kc[0])]) for group in out]


def _words(line: Line) -> list[list[int]]:
    words, cur = [], []
    for i, c in enumerate(line.chars):
        if c.text.isspace():
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(i)
    if cur:
        words.append(cur)
    return words


def visual_order(lines: list[Line]) -> int:
    """F9: each Hebrew word's letters sit at mirrored positions in the layer (letter k where letter n-1-k is drawn),
    as when a producer stores visual-order runs: a reader gets the word backwards. Returns the words changed."""
    changed = 0
    for line in lines:
        for word in _words(line):
            letters = [i for i in word if _rtl(line.chars[i].text)]
            if len(letters) < 2:
                continue
            boxes = [(line.chars[i].x0, line.chars[i].x1) for i in letters]
            for i, (x0, x1) in zip(letters, boxes[::-1]):
                line.chars[i] = replace(line.chars[i], x0=x0, x1=x1)
            changed += 1
    return changed


def split_runs(lines: list[Line], rng: random.Random, share: float = 0.3) -> int:
    """F5: about ``share`` of the words (two letters or more) get a gap inside them in the layer, so an extractor
    reads two words. The page itself is unchanged."""
    split = 0
    for line in lines:
        for word in _words(line):
            if len(word) >= 2 and rng.random() < share:
                cut = rng.randrange(1, len(word))
                for i in word[cut:]:  # the rest of the word moves away from its start by a word gap
                    line.chars[i].shift = SPLIT_GAP * line.size
                split += 1
    return split


def drop_dots(lines: list[Line]) -> int:
    """Missing "." glyphs: a decimal point between digits is drawn but not in the layer."""
    dropped = 0
    for line in lines:
        keep = []
        for i, c in enumerate(line.chars):
            near = [d.text for d in line.chars if d is not c and abs((d.x0 + d.x1) / 2 - (c.x0 + c.x1) / 2) < 2 * line.size]
            if c.text == "." and sum(t.isdigit() for t in near) >= 2:
                dropped += 1
                continue
            keep.append(c)
        line.chars = keep
    return dropped


def offset(lines: list[Line], dx: float, dy: float) -> None:
    """A layer misaligned with its page, as an OCR layer often is."""
    for line in lines:
        line.chars = [replace(c, x0=c.x0 + dx, x1=c.x1 + dx, y0=c.y0 + dy, y1=c.y1 + dy) for c in line.chars]


def apply(lines: list[Line], faults: list[str], seed: int) -> dict:
    """Apply the named faults in a fixed order; returns what each one did."""
    unknown = set(faults) - set(FAULTS)
    if unknown:
        raise ValueError(f"unknown faults: {sorted(unknown)}")
    rng = random.Random(f"layer-faults:{seed}")
    record: dict = {}
    if "drop_dots" in faults:
        record["drop_dots"] = drop_dots(lines)
    if "visual_order" in faults:
        record["visual_order"] = visual_order(lines)
    if "split_runs" in faults:
        record["split_runs"] = split_runs(lines, rng)
    if "hidden_ocr" in faults:
        dx, dy = rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5)
        offset(lines, dx, dy)
        record["hidden_ocr"] = {"dx": round(dx, 2), "dy": round(dy, 2)}
    return record


# ---------------------------------------------------------------- PDF steps (``faults`` extra + Ghostscript)

def read_chars(pdf: Path) -> list[list[Char]]:
    import pypdfium2 as pdfium

    pages = []
    for page in pdfium.PdfDocument(str(pdf)):
        tp = page.get_textpage()
        chars = []
        for i in range(tp.count_chars()):
            t = tp.get_text_range(i, 1)
            if not t or t in "\r\n" or ord(t[0]) < 32:
                continue
            l, b, r, top = tp.get_charbox(i, loose=True)
            if r > l and top > b:
                chars.append(Char(t, l, b, r, top))
            elif t == " " and chars:  # a space the reader generated: no box; placed in the gap it stands for below
                chars.append(Char(" ", 0.0, chars[-1].y0, 0.0, chars[-1].y1))
        for i, c in enumerate(chars):
            if c.text != " " or c.x1 > c.x0:
                continue
            prev = chars[i - 1]
            nxt = next((d for d in chars[i + 1:] if d.text != " "), None)
            w = 0.25 * (prev.y1 - prev.y0)
            if nxt is not None and nxt.x1 <= prev.x0:      # reading leftwards
                lo, hi = nxt.x1, prev.x0
            elif nxt is not None and nxt.x0 >= prev.x1:    # reading rightwards
                lo, hi = prev.x1, nxt.x0
            else:
                lo, hi = (prev.x0 - w, prev.x0) if _rtl(prev.text) else (prev.x1, prev.x1 + w)
            chars[i] = replace(c, x0=lo, x1=max(hi, lo + 0.1))
        pages.append(chars)
    return pages


def outlined(pdf: Path, out: Path) -> None:
    gs = shutil.which("gs")
    if gs is None:
        raise RuntimeError("Ghostscript (gs) is needed to outline the producer text")
    subprocess.run([gs, "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite", "-dNoOutputFonts",
                    f"-sOutputFile={out}", str(pdf)], check=True, capture_output=True)


def rasterised(pdf: Path, out: Path, dpi: int = 300) -> None:
    import pypdfium2 as pdfium
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    doc = pdfium.PdfDocument(str(pdf))
    c = canvas.Canvas(str(out))
    for page in doc:
        w, h = page.get_size()
        image = page.render(scale=dpi / 72).to_pil().convert("L")
        c.setPageSize((w, h))
        c.drawImage(ImageReader(image), 0, 0, w, h)
        c.showPage()
    c.save()


def write_layer(pages: list[tuple[float, float, list[Line]]], font: Path, out: Path) -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    name = "LayerFont"
    pdfmetrics.registerFont(TTFont(name, str(font)))
    ascent, descent = pdfmetrics.getAscentDescent(name, 1000)
    em = (ascent - descent) / 1000  # the font's line box, in font sizes
    c = canvas.Canvas(str(out))
    for w, h, lines in pages:
        c.setPageSize((w, h))
        placed = sorted(((ch, line.size) for line in lines for ch in line.chars), key=lambda cs: cs[0].k)
        text = c.beginText()
        text.setTextRenderMode(3)  # invisible
        for ch, line_size in placed:  # the producer's order, each character where it is drawn
            size = line_size / em      # the font size whose line box is the characters' box height
            text.setFont(name, size)
            advance = pdfmetrics.stringWidth(ch.text, name, size)
            if advance > 0:  # each glyph as wide as the character it stands for, so word gaps stay gaps
                text.setHorizScale(100.0 * max(ch.x1 - ch.x0, 0.1) / advance)
            dx = -ch.shift if _rtl(ch.text) else ch.shift  # a split gap moves leftwards in right-to-left text
            text.setTextOrigin(ch.x0 + dx, ch.y0 - descent / 1000 * size)
            text.textOut(ch.text)
        c.drawText(text)
        c.showPage()
    c.save()


def merge(base: Path, layer: Path, out: Path) -> None:
    from pypdf import PdfReader, PdfWriter

    w = PdfWriter(clone_from=str(base))
    for page, over in zip(w.pages, PdfReader(str(layer)).pages):
        page.merge_page(over)
    with open(out, "wb") as f:
        w.write(f)


def check_font(font: Path) -> str:
    """The font's family; it must be an open family and never a held-out one (unless rendering for evaluation)."""
    import hashlib

    from fontTools.ttLib import TTFont

    from hdocsyngen import fonts as F

    family = TTFont(font, lazy=True, fontNumber=0)["name"]
    family = family.getDebugName(16) or family.getDebugName(1) or ""
    sha = hashlib.sha256(font.read_bytes()).hexdigest()
    if family not in F.OPEN_FAMILIES:
        raise ValueError(f"{font.name}: family {family!r} is not an open family")
    if (family in F.HELD_OUT_FAMILIES or sha in F.HELD_OUT_SHA256) and not F.eval_render():
        raise ValueError(f"{font.name}: held out for evaluation; never in a training render")
    return family


def fault_pdf(pdf: Path, out: Path, font: Path, faults: list[str], seed: int) -> dict:
    """The producer PDF with its text layer faulted; returns the record (also written as OUT.faults.json)."""
    import pypdfium2 as pdfium

    family = check_font(font)

    sizes = [p.get_size() for p in pdfium.PdfDocument(str(pdf))]
    pages, record = [], []
    for k, ((w, h), chars) in enumerate(zip(sizes, read_chars(pdf))):
        lines = lines_from_chars(chars)
        record.append({"page": k + 1, **apply(lines, faults, seed * 1000 + k)})
        pages.append((w, h, lines))
    with tempfile.TemporaryDirectory() as tmp:
        base, layer = Path(tmp) / "base.pdf", Path(tmp) / "layer.pdf"
        (rasterised if "hidden_ocr" in faults else outlined)(pdf, base)
        write_layer(pages, font, layer)
        merge(base, layer, out)
    meta = {"source": pdf.name, "faults": faults, "seed": seed, "font": font.name, "font_family": family, "pages": record}
    Path(str(out) + ".faults.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def check(original: Path, faulted: Path, dpi: int = 150) -> list[dict]:
    """Per page: the share of pixels that render visibly differently (the page must look the same) and the layer's
    character counts before and after (what the faults changed)."""
    from collections import Counter

    import numpy as np
    import pypdfium2 as pdfium

    out = []
    a_doc, b_doc = pdfium.PdfDocument(str(original)), pdfium.PdfDocument(str(faulted))
    for k, (a, b) in enumerate(zip(a_doc, b_doc)):
        ra = np.asarray(a.render(scale=dpi / 72).to_pil().convert("L"), dtype=float)
        rb = np.asarray(b.render(scale=dpi / 72).to_pil().convert("L"), dtype=float)
        if ra.shape != rb.shape:
            raise ValueError(f"page {k + 1}: page sizes differ")
        ca = Counter(ch for ch in a.get_textpage().get_text_range() if not ch.isspace())
        cb = Counter(ch for ch in b.get_textpage().get_text_range() if not ch.isspace())
        out.append({"page": k + 1, "pixels_changed_pct": round(float((np.abs(ra - rb) > 64).mean() * 100), 4),
                    "chars_missing": dict(ca - cb), "chars_extra": dict(cb - ca)})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hdocsyngen.layer_faults", description=__doc__.split("\n")[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--font", type=Path, required=True, help="an open Hebrew font (never a held-out one)")
    ap.add_argument("--faults", required=True, help="comma-separated: " + ",".join(FAULTS))
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    print(json.dumps(fault_pdf(a.pdf, a.out, a.font, [f for f in a.faults.split(",") if f], a.seed), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
