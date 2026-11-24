"""PDF census and gold checks (design note §1 census, §3.3 checks 1, 3 and 4).

- `census(pdf)`: per page, what the producer did: fonts (subtype, ToUnicode), private-use share, stream-order signal,
  space handling, glyph-run lengths, StructTreeRoot, and the producer and creator strings. Census version
  `CENSUS_VERSION`; pipeline uses it as an oracle (expected T-class signals), not as a run-time input.
- `verify_pdf(doc, plain, twin, allowed_fonts)`: the gold checks:
  1. **fonts (hard):** every font in both PDFs must be one of the requested family's PostScript names;
  2. **geometry:** the twin and the plain PDF have the same glyph multiset per page (else the document fails); per
     block, shifts over 0.25 pt are recorded and over 1 pt mark `geometry_ok: false`;
  3. **text read-back:** each block's characters, found by its twin colour, match the gold's characters as a
     multiset (order-free, because a layer may be in visual order); the page(s) each block lands on are recorded;
  4. **pixels:** a block with text-layer characters but no pixels of its colour in the rendered twin is
     `not_rendered` (clipped or hidden).
- `read_text_layer(pdf, doc, twin)`: comparison of position-sorted pdfium, pdfminer, Poppler and PyMuPDF.
  An optional tree and colour twin let it also check that LTR tokens occupy increasing x slots within a block.

Characters are read with pdfium (pypdfium2); document structure (fonts, ToUnicode, StructTreeRoot) with pdfminer.six
(the `pdf` extra).
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .readers.pdf_read import mupdf_pages, poppler_pages
from .tree import Document, Run, colour_index, iter_paragraphs, text_of, twin_colours

CENSUS_VERSION = "census.v0"
SHIFT_RECORD_PT = 0.25      # twin shifts above this are recorded (coordinates are compared rounded to 0.1 pt)
GEOMETRY_OK_PT = 1.0        # above this, a block's twin geometry is `geometry_ok: false` (eval)
PARTIAL_CLIP_RATIO = 0.25   # pixels per glyph below this share of the median: `partially_rendered`
FINALS = set("ךםןףץ")
_WORD = re.compile(r"[א-ת]+")


@dataclass
class Glyph:
    """One character as pdfium reads it: text, box (PDF points, origin bottom-left), origin, fill colour, font."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    origin: tuple[float, float]
    rgb: tuple[int, int, int] | None
    fontname: str
    size: float
    unicode_error: bool

    def get_text(self) -> str:
        return self.text

    @property
    def matrix(self) -> tuple[float, ...]:
        return (1.0, 0.0, 0.0, 1.0, self.origin[0], self.origin[1])


def _stream_chars(pdf: Path):
    """(page_no, LTChar) in content-stream order, for order signals only (the census's T2 signal and glyph runs).

    pdfminer's interpreter emits characters in the order the producer wrote them (a page aggregator with
    laparams=None; extract_pages always runs layout analysis). Its glyph positions are not used: in Quartz PDFs it
    misplaces Hebrew glyphs (by up to 200 pt, found on pilot v0's Word PDFs).
    """
    from pdfminer.converter import PDFPageAggregator
    from pdfminer.layout import LTChar
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage

    def walk(o):
        if isinstance(o, LTChar):
            yield o
        elif hasattr(o, "__iter__"):
            for c in o:
                yield from walk(c)

    rm = PDFResourceManager()
    dev = PDFPageAggregator(rm, laparams=None)
    interp = PDFPageInterpreter(rm, dev)
    with open(pdf, "rb") as fh:
        for page_no, page in enumerate(PDFPage.get_pages(fh), start=1):
            interp.process_page(page)
            for ch in walk(dev.get_result()):
                yield page_no, ch


def _chars(pdf: Path):
    """(page_no, Glyph) read with pdfium (heocr's text engine), for positions, colours, fonts and text.

    pdfium places glyphs correctly where pdfminer does not (Quartz PDFs), but its text page reorders right-to-left
    text, so its order is not the stream order (use `_stream_chars` for that). Characters pdfium generates itself
    (spaces and line breaks it infers) are skipped.
    """
    import ctypes
    import pypdfium2 as pdfium
    import pypdfium2.raw as R

    doc = pdfium.PdfDocument(str(pdf))
    try:
        for page_no in range(1, len(doc) + 1):
            tp = doc[page_no - 1].get_textpage()
            raw = tp.raw
            buf = ctypes.create_string_buffer(256)
            flags = ctypes.c_int()
            for i in range(tp.count_chars()):
                if R.FPDFText_IsGenerated(raw, i) == 1:
                    continue
                u = R.FPDFText_GetUnicode(raw, i)
                if u in (0, 0xFFFE, 0xFFFF) or u in (10, 13):
                    continue
                l, rgt, b, t = (ctypes.c_double() for _ in range(4))
                R.FPDFText_GetCharBox(raw, i, l, rgt, b, t)
                ox, oy = ctypes.c_double(), ctypes.c_double()
                R.FPDFText_GetCharOrigin(raw, i, ox, oy)
                cr, cg, cb, ca = (ctypes.c_uint() for _ in range(4))
                ok = R.FPDFText_GetFillColor(raw, i, cr, cg, cb, ca)
                n = R.FPDFText_GetFontInfo(raw, i, buf, len(buf), flags)
                name = buf.raw[: max(0, n - 1)].decode("latin-1") if n else ""
                yield page_no, Glyph(chr(u), l.value, b.value, rgt.value, t.value, (ox.value, oy.value),
                                     (cr.value, cg.value, cb.value) if ok else None, name,
                                     R.FPDFText_GetFontSize(raw, i), bool(R.FPDFText_HasUnicodeMapError(raw, i)))
    finally:
        doc.close()


def _rgb255(ch) -> tuple[int, int, int] | None:
    """The fill colour as 0-255 RGB, from a pdfium Glyph or a pdfminer LTChar."""
    if isinstance(ch, Glyph):
        return ch.rgb
    col = ch.graphicstate.ncolor
    if col is None:
        return (0, 0, 0)
    if isinstance(col, (int, float)):
        col = (col, col, col)
    if len(col) == 1:
        col = (col[0],) * 3
    if len(col) != 3:
        return None
    return tuple(int(round(float(c) * 255)) for c in col)


def _doc_info(pdf: Path) -> dict:
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdftypes import resolve1

    def s(v):
        v = resolve1(v)
        if isinstance(v, bytes):
            if v.startswith(b"\xfe\xff"):
                return v[2:].decode("utf-16-be", "replace")
            return v.decode("latin-1")
        return str(v) if v is not None else None

    with open(pdf, "rb") as fh:
        d = PDFDocument(PDFParser(fh))
        info = d.info[0] if d.info else {}
        catalog = d.catalog
        pages = []
        for page in PDFPage.create_pages(d):
            fonts = []
            res = resolve1(page.resources) or {}
            for name, ref in (resolve1(res.get("Font")) or {}).items():
                f = resolve1(ref)
                sub = f.get("Subtype")
                base = f.get("BaseFont")
                if base is None:                          # Type3 fonts often have no BaseFont
                    desc = resolve1(f.get("FontDescriptor")) or {}
                    base = desc.get("FontName") or f.get("Name")
                tu = "ToUnicode" in f
                if getattr(sub, "name", None) == "Type0":
                    desc = resolve1(f.get("DescendantFonts"))[0]
                    sub = resolve1(desc).get("Subtype")
                fonts.append({"name": getattr(base, "name", str(base)), "subtype": getattr(sub, "name", str(sub)),
                              "tounicode": tu})
            pages.append(sorted(fonts, key=lambda x: x["name"]))
        return {"producer": s(info.get("Producer")), "creator": s(info.get("Creator")),
                "struct_tree": "StructTreeRoot" in catalog, "page_fonts": pages}


def census(pdf: Path) -> dict:
    info = _doc_info(pdf)
    per_page = defaultdict(list)
    for page_no, ch in _stream_chars(pdf):
        per_page[page_no].append(ch)
    pages = []
    for i, fonts in enumerate(info["page_fonts"], start=1):
        chs = per_page.get(i, [])
        text = "".join(c.get_text() for c in chs)
        letters = [c for c in text if not c.isspace()]
        pua = sum(1 for c in letters if 0xE000 <= ord(c) <= 0xF8FF)
        words = _WORD.findall(text)
        final_start = sum(1 for w in words if len(w) > 1 and w[0] in FINALS)
        final_end = sum(1 for w in words if len(w) > 1 and w[-1] in FINALS)
        # glyph runs: consecutive chars (stream order) on one baseline in one font
        runs, run = [], 0
        prev = None
        for c in chs:
            same = prev is not None and c.fontname == prev.fontname and abs(c.matrix[5] - prev.matrix[5]) < 0.5
            run = run + 1 if same else 1
            if not same and prev is not None:
                runs.append(prev_run)
            prev, prev_run = c, run
        if prev is not None:
            runs.append(prev_run)
        runs.sort()
        pages.append({
            "page": i, "fonts": fonts, "chars": len(letters),
            "pua_share": round(pua / len(letters), 4) if letters else 0.0,
            "space_chars_share": round(text.count(" ") / max(1, len(text)), 4),
            "final_at_word_start": final_start, "final_at_word_end": final_end,
            "t2_signal": round(final_start / max(1, final_start + final_end), 3),
            "median_glyph_run": runs[len(runs) // 2] if runs else 0,
            "single_glyph_runs_share": round(sum(1 for r in runs if r == 1) / len(runs), 3) if runs else 0.0,
            "fonts_without_tounicode": sum(1 for f in fonts if not f["tounicode"]),
            "type3_fonts": sum(1 for f in fonts if f["subtype"] == "Type3"),
        })
    return {"census": CENSUS_VERSION, "producer": info["producer"], "creator": info["creator"],
            "struct_tree": info["struct_tree"], "pages": pages}


MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<"}


def _fold(s: str) -> Counter:
    """Characters as a multiset, compatibility forms folded (NFKC): a producer may store a ligature such as U+FB01 for
    "fi" in its text layer. Each block records the ligatures it found (`ligatures`)."""
    return Counter(c for c in unicodedata.normalize("NFKC", s) if not c.isspace())


def _fold_brackets(c: Counter) -> Counter:
    """Each mirrored pair as one class: a producer may store a bracket as the glyph it draws (mirrored in RTL)."""
    out = Counter()
    for ch, n in c.items():
        out[min(ch, MIRROR.get(ch, ch))] += n
    return out


def _visual_lines(glyphs: list[Glyph]) -> list[str]:
    """Horizontal baselines from top to bottom, with glyph slots from left to right on each baseline."""
    lines: list[list[Glyph]] = []
    for glyph in sorted(glyphs, key=lambda g: -g.origin[1]):
        if not lines or lines[-1][0].origin[1] - glyph.origin[1] > 1.0:
            lines.append([])
        lines[-1].append(glyph)
    return ["".join(g.text for g in sorted(line, key=lambda g: g.origin[0])) for line in lines]


_LTR_TOKEN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9:/.,@_+#?&=%~-]*[A-Za-z0-9])?")
_BRACKET_CLASSES = str.maketrans({c: min(c, mirror) for c, mirror in MIRROR.items()})


def _slot_order(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text).translate(_BRACKET_CLASSES)
                   if not c.isspace() and unicodedata.category(c) not in ("Cf", "Mn", "Me"))


def _bidi_order(runs: list[Run], observed: str) -> dict[str, bool] | None:
    """Compare order only when the one visual line carries the tree's characters."""
    visual = _slot_order(observed)
    if Counter(visual) != Counter(_slot_order("".join(run.text for run in runs))):
        return None
    from bidi import get_display as rust_display
    from bidi.algorithm import get_display as python_display

    # Recreate the tree's direction instead of passing through any controls from source prose.
    logical = []
    for run in runs:
        text = "".join(c for c in run.text if unicodedata.category(c) != "Cf")
        logical.append(text if run.lang == "he" else f"\u202a{text}\u202c")
    text = "".join(logical)
    return {"python_bidi": visual == _slot_order(python_display(text, base_dir="R")),
            "rust_bidi": visual == _slot_order(rust_display(text, base_dir="R"))}


def _ltr_slots(doc: Document, twin_glyphs: list[tuple[int, Glyph]]) -> dict[str, dict]:
    colours = {colour_index(rgb): pid for pid, rgb in twin_colours(doc).items()}
    per_block: dict[str, dict[int, list[Glyph]]] = defaultdict(lambda: defaultdict(list))
    for page, glyph in twin_glyphs:
        pid = colours.get(colour_index(glyph.rgb)) if glyph.rgb is not None else None
        if pid is not None:
            per_block[pid][page].append(glyph)
    checks = {}
    for _, p in iter_paragraphs(doc):
        expected = Counter(token for run in p.runs if run.lang in ("en", "num") and run.field is None
                           for token in _LTR_TOKEN.findall(run.text) if token != token[::-1])
        if not expected:
            continue
        lines = [line for glyphs in per_block[p.id].values() for line in _visual_lines(glyphs)]
        observed = Counter(token for line in lines
                           for token in _LTR_TOKEN.findall(unicodedata.normalize("NFKC", line)))
        forward = expected & observed
        # Reserve exact matches first when a block contains both a token and its reverse.
        remaining = observed - forward
        reversed_count = sum(min(n, remaining[token[::-1]]) for token, n in (expected - forward).items())
        found = forward.total()
        checks[p.id] = {"forward": found, "reversed": reversed_count,
                        "unresolved": expected.total() - found - reversed_count}
        if len(lines) == 1 and not any(run.field for run in p.runs):
            order = _bidi_order(p.runs, lines[0])
            if order is not None:
                checks[p.id]["visual_order"] = order
    return checks


def _readback_sequence(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text).translate(_BRACKET_CLASSES)
                   if not c.isspace() and unicodedata.category(c) != "Cf")


def _reader_order(reference: str, observed: str, missing: int, extra: int) -> str:
    if missing or extra:
        return "different_inventory"
    if not reference:
        return "empty"
    return "same_sequence" if reference == observed else "different_sequence"


def read_text_layer(pdf: Path, doc: Document | None = None, twin: Path | None = None) -> dict:
    """Audit text-layer coverage per page and physical LTR token order in the colour twin.

    Reader deltas and sequence comparisons use PDFium's physical slots. A sequence difference is only classified
    when normalized character inventories agree. Physical order and emitted reader order can legitimately differ.
    The tree and its block survival checks remain the reference. The audit emits no extracted text.
    """
    if (doc is None) != (twin is None):
        raise ValueError("both the tree and its colour twin are required for the LTR check")
    visual: dict[int, list[Glyph]] = defaultdict(list)
    for page, glyph in _chars(pdf):
        visual[page].append(glyph)
    stream: dict[int, list[str]] = defaultdict(list)
    for page, glyph in _stream_chars(pdf):
        stream[page].append(glyph.get_text())
    poppler, mupdf = poppler_pages(pdf), mupdf_pages(pdf)
    if len(poppler) != len(mupdf):
        raise ValueError(f"read-back page count differs: Poppler {len(poppler)}, PyMuPDF {len(mupdf)}")
    pages = []
    for i, (poppler_text, mupdf_text) in enumerate(zip(poppler, mupdf, strict=True), 1):
        sequence = _readback_sequence("\n".join(_visual_lines(visual[i])))
        reference = Counter(sequence)
        readers, order = {}, {}
        for name, text in (("pdfminer", "".join(stream[i])), ("poppler", poppler_text), ("pymupdf", mupdf_text)):
            observed = _readback_sequence(text)
            chars = Counter(observed)
            missing, extra = (reference - chars).total(), (chars - reference).total()
            readers[name] = {"chars": chars.total(), "missing": missing, "extra": extra}
            order[name] = _reader_order(sequence, observed, missing, extra)
        pages.append({"page": i, "pdfium_visual_chars": reference.total(), "readers": readers, "reader_order": order})
    result = {"pages": pages}
    if doc is not None and twin is not None:
        result["ltr_slots"] = _ltr_slots(doc, list(_chars(twin)))
    return result


def _pixel_counts(pdf: Path, dpi: int = 150) -> Counter:
    """Pixels per twin colour index, rendered without anti-aliasing (so colours stay exact)."""
    import numpy as np
    import pypdfium2 as pdfium
    counts: Counter = Counter()
    doc = pdfium.PdfDocument(str(pdf))
    try:
        for i in range(len(doc)):
            bm = doc[i].render(scale=dpi / 72, no_smoothtext=True, no_smoothimage=True, no_smoothpath=True,
                               rev_byteorder=True)
            n = bm.n_channels
            a = np.frombuffer(bm.buffer, np.uint8).reshape(bm.height, bm.stride)[:, :bm.width * n]
            a = a.reshape(bm.height, bm.width, n)[:, :, :3].astype(np.int32)
            mask = (a.max(axis=2) <= 31) & (a.sum(axis=2) > 0)
            idx = (a[..., 0] << 10) | (a[..., 1] << 5) | a[..., 2]
            vals, cnt = np.unique(idx[mask], return_counts=True)
            for v, c in zip(vals.tolist(), cnt.tolist()):
                counts[v] += c
    finally:
        doc.close()
    return counts


def _page_values(doc: Document, twin_raw, colours: dict[int, str]) -> dict[str, list[dict]]:
    """The value each furniture field printed on each page (eval: the producer-basis reference for fields).

    A furniture paragraph's glyphs are found by its twin colour, per page. Runs of digit glyphs on one baseline form
    the printed numbers; they are assigned to the paragraph's fields in logical order, which in a right-to-left
    paragraph is right to left on the page. Digits inside a number read left to right.
    """
    from .gold import _fields
    out: dict[str, list[dict]] = {}
    furn = {p.id: p for p in doc.furniture.header + doc.furniture.footer}
    glyphs: dict[tuple[str, int], list] = defaultdict(list)
    loose: dict[int, list] = defaultdict(list)          # uncoloured digits per page: Word and LibreOffice redraw
    for page_no, ch in twin_raw:                         # field results without the run's colour
        pid = colours.get(colour_index(_rgb255(ch) or (255, 255, 255)))
        if pid in furn:
            glyphs[(pid, page_no)].append(ch)
        elif pid is None and ch.get_text().isdigit():
            loose[page_no].append(ch)
    for (pid, page_no), chs in sorted(glyphs.items(), key=lambda x: (x[0][0], x[0][1])):
        fields = _fields(furn[pid])
        if not fields:
            continue
        baselines = {round(c.matrix[5], 1) for c in chs}
        mine = [c for c in chs if c.get_text().isdigit()]
        mine += [c for c in loose.get(page_no, []) if any(abs(c.matrix[5] - y) < 1.0 for y in baselines)]
        digits = sorted(mine, key=lambda c: (round(c.matrix[5]), c.x0))
        clusters: list[list] = []
        for c in digits:
            last = clusters[-1][-1] if clusters else None
            if last is not None and abs(c.matrix[5] - last.matrix[5]) < 1 and -0.5 <= c.x0 - last.x1 < 0.5 * max(1.0, c.size):
                clusters[-1].append(c)
            else:
                clusters.append([c])
        clusters.sort(key=lambda cl: -cl[0].x0)                  # right to left: logical order in RTL
        rec = out.setdefault(pid, [])
        for f, cl in zip(fields, clusters):
            rec.append({"page": page_no, "field": f["kind"], "field_offset": f["offset"],
                        "text": "".join(c.get_text() for c in cl)})
    return out


def verify_pdf(doc: Document, plain: Path, twin: Path, allowed_fonts: set[str]) -> dict:
    """Problems (hard failures) and the observed layers: pages per block, not_rendered blocks."""
    problems: list[str] = []
    synthetic: set[str] = set()
    for label, pdf in (("plain", plain), ("twin", twin)):
        for page_fonts in _doc_info(pdf)["page_fonts"]:
            for f in page_fonts:
                base = f["name"].split("+", 1)[-1]
                if base in allowed_fonts:
                    continue
                # Word for Mac names a variable font's instance `PSName_Style` (e.g. Rubik-Light_Bold: the requested
                # face, with a synthesised style). That is the requested family, recorded as synthetic, not a
                # substitution.
                if "_" in base and base.split("_", 1)[0] in allowed_fonts:
                    synthetic.add(base)
                    continue
                problems.append(f"{label}: font {base} is not the requested family")
    problems = sorted(set(problems))
    colours = {colour_index(c): pid for pid, c in twin_colours(doc).items()}
    furniture = {p.id for p in doc.furniture.header + doc.furniture.footer}
    plain_chars = [(p, round(c.origin[0], 1), round(c.origin[1], 1), c.get_text()) for p, c in _chars(plain)]
    twin_raw = list(_chars(twin))
    twin_chars = [(p, round(c.origin[0], 1), round(c.origin[1], 1), c.get_text()) for p, c in twin_raw]
    # Per block: the largest shift of its glyphs between the plain PDF and the twin (eval, review of #2). Text gold does
    # not depend on colour, so only a different glyph multiset per page (a block changed page, or glyphs differ)
    # fails the document. A shift over SHIFT_RECORD_PT is recorded; over GEOMETRY_OK_PT the block's twin geometry is
    # marked `geometry_ok: false`. Order-free: producers may write the twin's glyphs in another stream order
    # (LibreOffice splits text portions by colour), so each twin glyph is matched to the nearest plain glyph with the
    # same page and character.
    owner = [colours.get(colour_index(_rgb255(c) or (255, 255, 255))) for _, c in twin_raw]
    grid: dict[tuple, list[tuple[float, float]]] = defaultdict(list)
    for pg, x, y, ch in plain_chars:
        grid[(pg, ch)].append((x, y))
    moved: dict[str, float] = {}
    shifted = 0
    if Counter((a[0], a[3]) for a in plain_chars if not a[3].isspace()) != \
            Counter((b[0], b[3]) for b in twin_chars if not b[3].isspace()):
        problems.append("geometry: the twin's glyph multiset per page differs from the plain PDF's")
    for (pg, x, y, ch), pid in zip(twin_chars, owner):
        if pid is None or pid in furniture or ch.isspace():
            continue
        cands = grid.get((pg, ch), [])
        d = min((max(abs(x - px), abs(y - py)) for px, py in cands), default=float("inf"))
        if d > SHIFT_RECORD_PT:
            shifted += 1
            moved[pid] = max(moved.get(pid, 0.0), round(d, 2) if d != float("inf") else 999.0)
    # Text, pages and page values by colour: read with pdfminer, whose fill colours are exact (pdfium sometimes gives
    # a Type3 glyph the colour of a neighbouring text object). Its glyph positions are used only within one PDF.
    twin_stream = list(_stream_chars(twin))
    got_text: dict[str, list[str]] = defaultdict(list)
    pages: dict[str, set[int]] = defaultdict(set)
    unattributed = Counter()
    for page_no, ch in twin_stream:
        rgb = _rgb255(ch)
        k = colour_index(rgb) if rgb else -1
        pid = colours.get(k)
        if pid is None:
            unattributed[ch.get_text()] += 1
            continue
        got_text[pid].append(ch.get_text())
        pages[pid].add(page_no)
    page_values = _page_values(doc, twin_stream, colours)
    pixels = _pixel_counts(twin)
    blocks, not_rendered = {}, []
    density: dict[str, float] = {}
    by_colour = twin_colours(doc)
    for container, p in iter_paragraphs(doc):
        exp = _fold(text_of(p))
        got = _fold("".join(got_text.get(p.id, [])))
        if container in ("header", "footer"):
            # furniture repeats on every page; check one copy is there
            per_page = max(1, len(pages.get(p.id, ())) or 1)
            got = Counter({c: n // per_page for c, n in got.items()})
        # Brackets are compared as mirrored pairs; whether the producer stored the logical bracket or its mirror
        # (the glyph drawn in RTL) is recorded per block (`brackets`).
        missing = _fold_brackets(exp) - _fold_brackets(got)
        extra = _fold_brackets(got) - _fold_brackets(exp)
        # Survival only (eval): a block that matches only after NFKC folding is recorded; scoring keeps line_fold_v1.
        exp_nfc = _fold_brackets(Counter(c for c in unicodedata.normalize("NFC", text_of(p)) if not c.isspace()))
        got_nfc = _fold_brackets(Counter(c for c in unicodedata.normalize("NFC", "".join(got_text.get(p.id, [])))
                                         if not c.isspace()))
        bexp = {b: exp[b] for b in MIRROR if exp[b]}
        bgot = {b: got[b] for b in MIRROR if got[b]}
        entry = {"pages": sorted(pages.get(p.id, ())), "missing_chars": sum(missing.values()),
                 "extra_chars": sum(extra.values()),
                 "geometry_ok": moved.get(p.id, 0.0) <= GEOMETRY_OK_PT}
        if bexp and bexp != bgot:
            entry["brackets"] = {"gold": bexp, "layer": bgot}
        if not missing and exp_nfc - got_nfc:
            entry["nfkc_only"] = True
        ligs = sum(1 for ch in got_text.get(p.id, []) if unicodedata.normalize("NFKC", ch) != ch and len(unicodedata.normalize("NFKC", ch)) > 1)
        if ligs:
            entry["ligatures"] = ligs
        px = pixels.get(colour_index(by_colour[p.id]), 0)
        n_glyphs = sum(exp.values())
        if exp and px == 0:
            entry["not_rendered"] = True
            not_rendered.append(p.id)
        elif n_glyphs:
            density[p.id] = px / n_glyphs
        blocks[p.id] = entry
        if missing and not entry.get("not_rendered") and container not in ("header", "footer"):
            problems.append(f"{p.id}: {sum(missing.values())} gold characters not in the text layer")
    # Partial clipping (heuristic): a block whose pixels per glyph fall below PARTIAL_CLIP_RATIO of the document's
    # median is `partially_rendered` (part of it clipped or hidden). Furniture is left out (repeated per page).
    body_density = sorted(v for k, v in density.items() if k not in furniture)
    partial = []
    if body_density:
        med = body_density[len(body_density) // 2]
        for pid, v in density.items():
            if pid not in furniture and v < PARTIAL_CLIP_RATIO * med:
                blocks[pid]["partially_rendered"] = True
                partial.append(pid)
    mirrored = sum(1 for b in blocks.values() if "brackets" in b)
    ligatures = sum(b.get("ligatures", 0) for b in blocks.values())
    return {"problems": problems, "blocks": blocks, "not_rendered": not_rendered, "partially_rendered": partial,
            "synthetic_style_fonts": sorted(synthetic), "blocks_with_bracket_change": mirrored,
            "ligature_chars": ligatures,
            "glyphs_moved": shifted,
            "moved_blocks": moved, "page_values": page_values,
            "unattributed_chars": sum(unattributed.values()),
            "unattributed_sample": "".join(sorted(unattributed))[:60]}


def verify_chain(doc: Document, input_plain: Path, input_twin: Path, output: Path) -> dict:
    """Gold survival through a chain step that may change colours or fonts (P8 Ghostscript, design note §1).

    The step's own twin is not trusted (a colour conversion breaks it). Each output glyph is attributed instead by
    position: to the nearest input glyph (same page, glyph origin within 1.5 pt) whose block is known from the input's twin. The
    result is an observation, not a pass or fail: the output's text-layer state and each block's survival.
    - `text_layer`: `none` (no characters), `broken` (characters come out, but over 20% are unknown codes or under 90%
      of blocks survive whole), or `intact`;
    - per block: characters found, missing and extra (multiset, brackets and NFKC folded, as verify_pdf).
    """
    colours = {colour_index(c): pid for pid, c in twin_colours(doc).items()}
    owner_at: dict[int, list[tuple[float, float, str]]] = defaultdict(list)
    plain_in = list(_chars(input_plain))
    twin_in = list(_chars(input_twin))
    # the input twin attributes positions to blocks; the input plain has the same glyph positions (verify_pdf)
    for (pg, c) in twin_in:
        pid = colours.get(colour_index(_rgb255(c) or (255, 255, 255)))
        if pid is not None:
            # the glyph origin (pdfium): independent of the font's metrics, which a chain step may change
            owner_at[pg].append((c.origin[0], c.origin[1], pid))
    out_chars = list(_chars(output))
    got: dict[str, list[str]] = defaultdict(list)
    unmapped = Counter()
    unknown = 0
    for pg, c in out_chars:
        t = c.get_text()
        if t.startswith("(cid:") or (len(t) == 1 and 0xE000 <= ord(t) <= 0xF8FF):
            unknown += 1
        best, bd = None, 1.5
        ox, oy = c.origin
        for x, y, pid in owner_at.get(pg, ()):
            d = max(abs(x - ox), abs(y - oy))
            if d < bd:
                best, bd = pid, d
        if best is None:
            unmapped[t] += 1
        else:
            got[best].append(t)
    n = len(out_chars)
    blocks = {}
    survived = 0
    for container, p in iter_paragraphs(doc):
        if container in ("header", "footer"):
            continue
        exp = _fold_brackets(_fold(text_of(p)))
        g = _fold_brackets(_fold("".join(got.get(p.id, []))))
        missing, extra = exp - g, g - exp
        blocks[p.id] = {"missing_chars": sum(missing.values()), "extra_chars": sum(extra.values())}
        survived += int(not missing)
    in_n = len(plain_in)
    # `broken`: characters come out, but most blocks lose some (lost or wrong ToUnicode, cid codes, private use)
    if n == 0:
        state = "none"
    elif unknown > 0.2 * n or survived < 0.9 * max(1, len(blocks)):
        state = "broken"
    else:
        state = "intact"
    return {"text_layer": state, "chars_in": in_n, "chars_out": n, "unknown_chars": unknown,
            "unmapped_chars": sum(unmapped.values()), "blocks_survived": survived, "blocks": blocks,
            "fonts": [f for pf in _doc_info(output)["page_fonts"] for f in pf]}
