"""Fail-closed per-page ground truth for single-column native document trees."""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
import subprocess
import unicodedata

from .fonts import HELD_OUT_FAMILIES, HELD_OUT_SHA256, OPEN_FAMILIES, FontFile
from .pdfcheck import Glyph, _chars
from .readers.literal_pdf import matching_glyph, painted_pages, pdfminer_pages, position_index
from .readers.pdf_read import poppler_pages
from .tree import Document, Heading, PageBreak, Paragraph, text_of, validate

PARTNERS = dict(zip("()[]“”", ")(][”“", strict=True))
PUNCTUATION_CLASSES = str.maketrans({char: min(char, partner) for char, partner in PARTNERS.items()})
READER_CONTROLS = str.maketrans("", "", "\u200e\u200f\u202a\u202b\u202c\u2066\u2067\u2068\u2069")


def literal(text: str) -> str:
    return "".join(char for char in text if not char.isspace())


def source_pages(tree: Document) -> list[list[Paragraph | Heading]]:
    """Take literal block text from the tree in its declared page order."""
    problems = validate(tree)
    if problems:
        raise ValueError(f"Invalid input tree: {problems[0]}")
    if tree.meta.columns != 1 or tree.notes or tree.furniture.header or tree.furniture.footer:
        raise ValueError("Literal line audit expects single-column body text")
    pages = [[]]
    for block in tree.body:
        if isinstance(block, PageBreak) and pages[-1]:
            pages.append([])
            continue
        if not isinstance(block, (Paragraph, Heading)) or block.num or block.notes:
            raise ValueError("Literal line audit expects unnumbered text blocks with explicit page breaks")
        if not literal(text_of(block)) or any(
            run.field or any(unicodedata.category(char) == "Cf" for char in run.text) for run in block.runs
        ):
            raise ValueError(f"Empty or nonliteral source block: {block.id}")
        pages[-1].append(block)
    if not pages[-1]:
        raise ValueError("Empty source page")
    return pages


def declared_glyphs(family: str, faces: tuple[FontFile, ...]) -> dict[str, frozenset[str]]:
    from fontTools.ttLib import TTFont

    if family not in OPEN_FAMILIES or family in HELD_OUT_FAMILIES or not faces:
        raise ValueError("A declared open TRAIN font family is required")
    declared = {}
    for face in faces:
        source = Path(face.path)
        if face.family != family or face.sha256 in HELD_OUT_SHA256:
            raise ValueError("Unexpected or reserved font in the declared family")
        if sha256(source.read_bytes()).hexdigest() != face.sha256:
            raise ValueError("Declared font file differs from its pin")
        with TTFont(source) as font:
            names = font["name"]
            if (names.getDebugName(16) or names.getDebugName(1)) != family or names.getDebugName(6) != face.postscript:
                raise ValueError("Declared font face identity differs from its bytes")
            chars = frozenset(chr(code) for code, glyph in (font.getBestCmap() or {}).items()
                              if glyph != ".notdef" and font.getGlyphID(glyph) > 0)
        for name in (face.postscript, *face.instances):
            if name in declared and declared[name] != chars:
                raise ValueError(f"Ambiguous declared font: {name}")
            declared[name] = chars
    return declared


def _visual_rows(glyphs: list[Glyph]) -> list[list[Glyph]]:
    rows = []
    for glyph in sorted(glyphs, key=lambda ch: -ch.origin[1]):
        if not rows or rows[-1][0].origin[1] - glyph.origin[1] > 1.1:
            rows.append([])
        rows[-1].append(glyph)
    return [sorted(row, key=lambda ch: ch.origin[0]) for row in rows]


def _source_visual(block, start: int, stop: int) -> set[str]:
    from bidi import get_display as paired_display
    from bidi.algorithm import get_display

    whole = text_of(block)[start:stop]
    directed = []
    offset = 0
    for run in block.runs:
        end = offset + len(run.text)
        if offset < stop and end > start:
            part = run.text[max(start-offset, 0):min(stop-offset, len(run.text))]
            directed.append(part if run.lang == "he" else "\u202a" + part + "\u202c")
        offset = end
    # Legacy display applies mirroring. The paired-bracket implementation also
    # supplies logical glyph-codepoint order for native producer text layers.
    return {
        literal(get_display(whole, base_dir="R")),
        literal(get_display("".join(directed), base_dir="R")),
        literal(paired_display(whole, base_dir="R").translate(READER_CONTROLS)),
    }


def _confirm(row, expected, painted, declared):
    for glyph in row:
        face = glyph.fontname.split("+", 1)[-1]
        if face not in declared or glyph.text not in declared[face] or glyph.unicode_error:
            raise ValueError("Unexpected font, missing declared glyph or invalid PDF Unicode mapping")
    raw = "".join(glyph.text for glyph in row)
    if raw in expected:
        return raw, []

    matches = []
    for candidate in sorted(expected):
        if len(candidate) != len(row):
            continue
        witnesses = []
        for slot, (glyph, wanted) in enumerate(zip(row, candidate, strict=True)):
            if glyph.text == wanted:
                continue
            face = glyph.fontname.split("+", 1)[-1]
            if PARTNERS.get(glyph.text) != wanted or wanted not in declared[face]:
                break
            witness = matching_glyph(painted, glyph.origin)
            if not witness or witness.glyph_id <= 0 or witness.face != face or witness.text != wanted:
                break
            witnesses.append({
                "slot": slot,
                "from": f"U+{ord(glyph.text):04X}",
                "to": f"U+{ord(wanted):04X}",
                "postscript_face": face,
                "glyph_id": witness.glyph_id,
                "origin_pt_bottom_left": list(witness.origin),
            })
        else:
            matches.append((candidate, witnesses))
    if len(matches) != 1:
        raise ValueError("PDF glyph order has no unique literal match")
    return matches[0]


def _verified_lines(rows, blocks, painted, declared):
    groups = iter(rows)
    for block in blocks:
        source = text_of(block)
        positions = [i for i, char in enumerate(source) if not char.isspace()]
        consumed = 0
        while consumed < len(positions):
            row = next(groups, None)
            if row is None or consumed + len(row) > len(positions):
                raise ValueError(f"PDF glyph count does not match source block {block.id}")
            end = consumed + len(row)
            start, stop = positions[consumed], positions[end - 1] + 1
            expected = _source_visual(block, start, stop)
            try:
                observed, witnesses = _confirm(row, expected, painted, declared)
            except ValueError as exc:
                raise ValueError(f"Source block {block.id}: {exc}") from exc
            yield {
                "block_id": block.id, "text": source[start:stop],
                "bbox_pt_bottom_left": [
                    min(g.x0 for g in row), min(g.y0 for g in row),
                    max(g.x1 for g in row), max(g.y1 for g in row),
                ],
                "confirmed_visual_codepoints": observed,
                "punctuation_glyph_witnesses": witnesses,
            }
            consumed = end
    if next(groups, None) is not None:
        raise ValueError("Additional PDF lines after the last declared source block")


def _crosscheck(lines, streams):
    text = "".join(literal(line["text"]) for line in lines)
    expected = Counter(text.translate(PUNCTUATION_CLASSES))
    visual = "".join(line["confirmed_visual_codepoints"] for line in lines)
    checks = {}
    for reader, observed in streams.items():
        observed = literal(observed.translate(READER_CONTROLS))
        if Counter(observed.translate(PUNCTUATION_CLASSES)) != expected:
            raise ValueError(f"{reader} glyph coverage differs from the source page")
        sequence = "logical" if observed == text else "visual" if observed == visual else "different_stream_order"
        checks[reader] = {"glyphs": len(observed), "sequence": sequence}
    return checks


def reader_versions() -> dict[str, str]:
    import pypdfium2 as pdfium

    poppler = subprocess.run(["pdftotext", "-v"], check=True, capture_output=True, text=True, timeout=30)
    return {
        **{dep: version(dep) for dep in ("pypdfium2", "pdfminer.six", "PyMuPDF", "python-bidi")},
        "pdfium": str(pdfium.PDFIUM_INFO),
        "poppler": (poppler.stderr or poppler.stdout).splitlines()[0],
    }


def verify_pdf(path: Path, tree: Document, faces: tuple[FontFile, ...]) -> dict:
    """Read positioned PDFium lines and verify literal gold against the source tree."""
    expected_pages = source_pages(tree)
    declared = declared_glyphs(tree.meta.font, faces)
    by_page = defaultdict(list)
    for page, glyph in _chars(path):
        if not glyph.text.isspace():
            by_page[page].append(glyph)
    meta, painted = painted_pages(path)
    minerals, poppler = pdfminer_pages(path), poppler_pages(path)
    if not len(expected_pages) == len(painted) == len(minerals) == len(poppler):
        raise ValueError("Native PDF page count differs from the source or independent readers")
    pages = []
    for number, (blocks, trace, miner, pop) in enumerate(zip(expected_pages, painted, minerals, poppler, strict=True), 1):
        try:
            rows = _visual_rows(by_page[number])
            lines = list(_verified_lines(rows, blocks, position_index(trace), declared))
            crosscheck = _crosscheck(lines, {
                "pdfminer": miner, "poppler": pop, "pymupdf": "".join(g.text for g in trace),
            })
        except ValueError as exc:
            raise ValueError(f"Page {number}: {exc}") from exc
        counts = Counter(f'{edge["from"]}->{edge["to"]}' for line in lines for edge in line["punctuation_glyph_witnesses"])
        pages.append({
            "page": number, "lines": lines, "reader_agreement": crosscheck,
            "check_method": "punct_recovered" if counts else "pdfium_exact",
            "recovered_codepoint_counts": dict(counts),
        })
    return {
        "pdf_sha256": sha256(path.read_bytes()).hexdigest(),
        "pdf_producer_signature": meta["producer"],
        "pdf_creator": meta["creator"],
        "pages": pages,
    }
