"""PDF census and gold checks (design note §1 census, §3.3 checks 1, 3 and 4).

- `census(pdf)`: per page, what the producer did: fonts (subtype, ToUnicode), private-use share, stream-order signal,
  space handling, glyph-run lengths, StructTreeRoot, and the producer and creator strings. Census version
  `CENSUS_VERSION`; pipeline uses it as an oracle (expected T-class signals), not as a run-time input.
- `verify_pdf(doc, plain, twin, allowed_fonts)`: the gold checks:
  1. **fonts (hard):** every font in both PDFs must be one of the requested family's PostScript names;
  2. **geometry:** the twin and the plain PDF place the same glyphs at the same positions (within 0.1 pt);
  3. **text read-back:** each block's characters, found by its twin colour, match the gold's characters as a
     multiset (order-free, because a layer may be in visual order); the page(s) each block lands on are recorded;
  4. **pixels:** a block with text-layer characters but no pixels of its colour in the rendered twin is
     `not_rendered` (clipped or hidden).

Needs pdfminer.six and pypdfium2 (the `pdf` extra).
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from .tree import Document, colour_index, iter_paragraphs, text_of, twin_colours

CENSUS_VERSION = "census.v0"
FINALS = set("ךםןףץ")
_WORD = re.compile(r"[א-ת]+")


def _chars(pdf: Path):
    """(page_no, LTChar) in content-stream order (no layout analysis)."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar

    def walk(o):
        if isinstance(o, LTChar):
            yield o
        elif hasattr(o, "__iter__"):
            for c in o:
                yield from walk(c)

    for page_no, page in enumerate(extract_pages(str(pdf), laparams=None), start=1):
        for ch in walk(page):
            yield page_no, ch


def _rgb255(ch) -> tuple[int, int, int] | None:
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
    for page_no, ch in _chars(pdf):
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
            same = prev is not None and c.fontname == prev.fontname and abs(c.y0 - prev.y0) < 0.5
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


def _fold(s: str) -> Counter:
    return Counter(c for c in unicodedata.normalize("NFC", s) if not c.isspace())


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
        baselines = {round(c.y0, 1) for c in chs}
        mine = [c for c in chs if c.get_text().isdigit()]
        mine += [c for c in loose.get(page_no, []) if any(abs(c.y0 - y) < 1.0 for y in baselines)]
        digits = sorted(mine, key=lambda c: (round(c.y0), c.x0))
        clusters: list[list] = []
        for c in digits:
            last = clusters[-1][-1] if clusters else None
            if last is not None and abs(c.y0 - last.y0) < 1 and 0 <= c.x0 - last.x1 < 0.5 * max(1.0, c.size):
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
    for label, pdf in (("plain", plain), ("twin", twin)):
        for page_fonts in _doc_info(pdf)["page_fonts"]:
            for f in page_fonts:
                base = f["name"].split("+", 1)[-1]
                if base not in allowed_fonts:
                    problems.append(f"{label}: font {base} is not the requested family")
    problems = sorted(set(problems))
    colours = {colour_index(c): pid for pid, c in twin_colours(doc).items()}
    furniture = {p.id for p in doc.furniture.header + doc.furniture.footer}
    plain_chars = [(p, round(c.x0, 1), round(c.y0, 1), c.get_text()) for p, c in _chars(plain)]
    twin_raw = list(_chars(twin))
    twin_chars = [(p, round(c.x0, 1), round(c.y0, 1), c.get_text()) for p, c in twin_raw]
    # Per block: the largest shift of its glyphs between the plain PDF and the twin. A colour change can move a
    # glyph by rounding, a page field, or (LibreOffice) a footnote line by a few points. The twin's geometry is then
    # off by that much, which is recorded; a block that changes page or moves more than 3 pt fails the document.
    # Order-free: producers may write the twin's glyphs in another stream order (LibreOffice splits text portions by
    # colour), so each twin glyph is matched to the nearest plain glyph with the same page and character.
    owner = [colours.get(colour_index(_rgb255(c) or (255, 255, 255))) for _, c in twin_raw]
    grid: dict[tuple, list[tuple[float, float]]] = defaultdict(list)
    for pg, x, y, ch in plain_chars:
        grid[(pg, ch)].append((x, y))
    moved: dict[str, float] = {}
    lost: set[str] = set()
    shifted = 0
    if Counter((a[0], a[3]) for a in plain_chars) != Counter((b[0], b[3]) for b in twin_chars):
        problems.append("geometry: the twin's glyphs (per page) differ from the plain PDF's")
    for (pg, x, y, ch), pid in zip(twin_chars, owner):
        if pid is None or pid in furniture or ch.isspace():
            continue
        cands = grid.get((pg, ch), [])
        d = min((max(abs(x - px), abs(y - py)) for px, py in cands), default=None)
        if d is None or d > 3.0:
            lost.add(pid)
        elif d > 0.25:
            shifted += 1
            moved[pid] = max(moved.get(pid, 0.0), round(d, 2))
    if lost:
        problems.append(f"geometry: {len(lost)} blocks have glyphs more than 3 pt from any plain glyph")
    got_text: dict[str, list[str]] = defaultdict(list)
    pages: dict[str, set[int]] = defaultdict(set)
    unattributed = Counter()
    for page_no, ch in twin_raw:
        rgb = _rgb255(ch)
        k = colour_index(rgb) if rgb else -1
        pid = colours.get(k)
        if pid is None:
            unattributed[ch.get_text()] += 1
            continue
        got_text[pid].append(ch.get_text())
        pages[pid].add(page_no)
    page_values = _page_values(doc, twin_raw, colours)
    pixels = _pixel_counts(twin)
    blocks, not_rendered = {}, []
    by_colour = twin_colours(doc)
    for container, p in iter_paragraphs(doc):
        exp = _fold(text_of(p))
        got = _fold("".join(got_text.get(p.id, [])))
        if container in ("header", "footer"):
            # furniture repeats on every page; check one copy is there
            per_page = max(1, len(pages.get(p.id, ())) or 1)
            got = Counter({c: n // per_page for c, n in got.items()})
        missing = exp - got
        extra = got - exp
        entry = {"pages": sorted(pages.get(p.id, ())), "missing_chars": sum(missing.values()),
                 "extra_chars": sum(extra.values())}
        if exp and pixels.get(colour_index(by_colour[p.id]), 0) == 0:
            entry["not_rendered"] = True
            not_rendered.append(p.id)
        blocks[p.id] = entry
        if missing and not entry.get("not_rendered") and container not in ("header", "footer"):
            problems.append(f"{p.id}: {sum(missing.values())} gold characters not in the text layer")
    return {"problems": problems, "blocks": blocks, "not_rendered": not_rendered, "glyphs_moved": shifted,
            "moved_blocks": moved, "page_values": page_values,
            "unattributed_chars": sum(unattributed.values()),
            "unattributed_sample": "".join(sorted(unattributed))[:60]}
