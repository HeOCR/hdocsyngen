"""Verify intent, literal glyphs and reading order for a structured native page."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from .fonts import FontFile
from .literal_verify import (
    _crosscheck, _verified_lines, _visual_rows, declared_glyphs, literal,
)
from .pdfcheck import Glyph, _chars
from .readers.literal_pdf import painted_pages, pdfminer_pages, position_index
from .readers.pdf_read import poppler_pages
from .tree import Document, Heading, Paragraph, Run, text_of, validate

# PDF points from the bottom or top of the page. These bands match the native
# page writers' margins for this fixed-page pilot.
FURNITURE_PT = 49
NOTE_CEILING_PT = 100


def body_columns(tree: Document, second_column_at: str | None) -> list[list[Paragraph | Heading]]:
    problems = validate(tree)
    if problems:
        raise ValueError(f"Invalid source tree: {problems[0]}")
    if any(not isinstance(block, (Heading, Paragraph)) for block in tree.body) or not tree.body:
        raise ValueError("Native page layout requires prose blocks on one page")
    if any(block.num for block in tree.body):
        raise ValueError("Use explicit, literal labels for the native page layout")
    if any(note.kind != "footnote" or len(note.paragraphs) != 1 for note in tree.notes) or len(tree.notes) > 1:
        raise ValueError("Native page layout supports one short footnote")
    if len(tree.furniture.header) > 1 or len(tree.furniture.footer) > 1:
        raise ValueError("Native page layout uses one running head and footer")
    if tree.meta.orientation != "portrait":
        raise ValueError("Native page layout requires portrait paper")
    if tree.meta.columns == 1 and second_column_at is None:
        return [tree.body]
    ids = [block.id for block in tree.body]
    if tree.meta.columns != 2 or second_column_at not in ids[1:]:
        raise ValueError("Two column pages require an explicit second-column anchor")
    cut = ids.index(second_column_at)
    return [tree.body[:cut], tree.body[cut:]]


def _blocks_for_verification(tree, column_groups):
    note_ids = {note.id: index for index, note in enumerate(tree.notes, 1)}
    content = {}
    for column in column_groups:
        for block in column:
            runs = list(block.runs)
            for anchor in sorted(block.notes, key=lambda a: a.offset, reverse=True):
                offset = 0
                for i, run in enumerate(runs):
                    end = offset + len(run.text)
                    if offset <= anchor.offset <= end:
                        k = anchor.offset - offset
                        runs[i:i+1] = [
                            replace(run, text=run.text[:k]), Run(str(note_ids[anchor.note_id]), "num"),
                            replace(run, text=run.text[k:]),
                        ]
                        break
                    offset = end
            content[block.id] = replace(block, runs=runs)
    for block in (*tree.furniture.header, *tree.furniture.footer):
        content[block.id] = replace(block, runs=[replace(run, text="1", field=None) if run.field else run
                                                 for run in block.runs])
    for note in tree.notes:
        block = note.paragraphs[0]
        content[block.id] = replace(block, runs=[Run(f"{note_ids[note.id]} ", "num"), *block.runs])
    return content


def _layout_rows(glyphs: list[Glyph]) -> list[list[Glyph]]:
    rows = _visual_rows(glyphs)
    # Office and browser footnote marks sit on a raised baseline. Merge an
    # isolated small digit run into a unique nearby text baseline.
    candidates = []
    for index, row in enumerate(rows):
        if len(row) > 2 or not all(g.text.isascii() and g.text.isdigit() for g in row):
            continue
        y = row[0].origin[1]
        x0, x1 = row[0].x0, row[-1].x1
        matches = [
            j for j, main in enumerate(rows) if j != index
            and 1.1 < y - main[0].origin[1] < 9
            and max(g.y1 - g.y0 for g in row) <= max(g.y1 - g.y0 for g in main) * .92
            and max(main[0].x0 - x1, x0 - main[-1].x1, 0) < 13
        ]
        if len(matches) == 1:
            candidates.append((index, matches[0]))
    gone = {i for i, _ in candidates}
    for i, j in candidates:
        if j in gone:
            raise ValueError("Ambiguous superscript rows")
        rows[j] = sorted([*rows[j], *rows[i]], key=lambda glyph: glyph.origin[0])
    return [row for i, row in enumerate(rows) if i not in gone]


def _bbox(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _regions(glyphs, columns, tree, width, height, positions, faces):
    heading = []
    footer = []
    notes = []
    body = [[] for _ in columns]
    for glyph in glyphs:
        x, y = glyph.origin
        if not 0 <= x <= width or not 0 <= y <= height:
            raise ValueError("Glyph origin is outside the page")
        if y >= height - FURNITURE_PT:
            heading.append(glyph)
        elif y <= FURNITURE_PT:
            footer.append(glyph)
        elif tree.notes and y < NOTE_CEILING_PT:
            notes.append(glyph)
        else:
            body[0 if len(columns) == 1 or x >= width / 2 else 1].append(glyph)

    expected = _blocks_for_verification(tree, columns)
    zones = [("header", None, tree.furniture.header, heading)]
    zones.extend(("body", ("right", "left")[i] if len(columns) == 2 else None, col, body[i])
                 for i, col in enumerate(columns))
    zones.extend([
        ("footnote", None, [note.paragraphs[0] for note in tree.notes], notes),
        ("footer", None, tree.furniture.footer, footer),
    ])
    for role, half, blocks, observed in zones:
        try:
            lines = list(_verified_lines(_layout_rows(observed), [expected[block.id] for block in blocks],
                                         positions, faces))
        except ValueError as exc:
            raise ValueError(f"{role}{'/' + half if half else ''}: {exc}") from exc
        at = 0
        for block in blocks:
            start = at
            while at < len(lines) and lines[at]["block_id"] == block.id:
                at += 1
            owned = lines[start:at]
            box = _bbox([line["bbox_pt_bottom_left"] for line in owned])
            kind = "heading" if isinstance(block, Heading) else "list_item" if block.style == "list" else "text"
            out = {"source_id": block.id, "role": role, "kind": kind,
                   "text": text_of(expected[block.id]), "bbox_pt_bottom_left": box, "lines": owned}
            if half:
                out["half"] = half
            if isinstance(block, Heading):
                out["level"] = block.level
            if kind == "list_item":
                out["label"] = block.runs[0].text.strip()
            if block.notes:
                out["note_refs"] = [{"kind": "footnote", "offset": link.offset} for link in block.notes]
                out["note_id"] = block.notes[0].note_id
            if role == "footnote":
                out["note_id"] = tree.notes[0].id
            yield out


def verify_page(path: Path, tree: Document, faces: tuple[FontFile, ...], second_column_at: str | None = None) -> dict:
    """Extract exact per-region and line geometry in PDF points, strictly in source order."""
    import pypdfium2 as pdfium

    columns = body_columns(tree, second_column_at)
    declared = declared_glyphs(tree.meta.font, faces)
    metadata, painted = painted_pages(path)
    minerals, poppler = pdfminer_pages(path), poppler_pages(path)
    if not len(painted) == len(minerals) == len(poppler) == 1:
        raise ValueError("Expected exactly one rendered page in every reader")
    with pdfium.PdfDocument(str(path)) as document:
        page = document[0]
        width, height = page.get_size()
        page.close()
    glyphs = [glyph for _, glyph in _chars(path) if not glyph.text.isspace()]
    regions = list(_regions(glyphs, columns, tree, width, height, position_index(painted[0]), declared))
    lines = [line for region in regions for line in region["lines"]]
    coverage = _crosscheck(lines, {"pdfminer": minerals[0], "poppler": poppler[0],
                                  "pymupdf": "".join(g.text for g in painted[0])})
    recovery = Counter(f'{edge["from"]}->{edge["to"]}' for line in lines for edge in line["punctuation_glyph_witnesses"])
    if sum(len(literal(line["text"])) for line in lines) != len(glyphs):
        raise ValueError("A rendered glyph was not assigned exactly once")
    return {
        "pdf_sha256": sha256(path.read_bytes()).hexdigest(),
        "pdf_producer_signature": metadata["producer"], "pdf_creator": metadata["creator"],
        "pages": [{
            "page": 1, "width_pt": width, "height_pt": height, "regions": regions,
            "lines": lines, "reader_agreement": coverage,
            "check_method": "punct_recovered" if recovery else "pdfium_exact",
            "recovered_codepoint_counts": dict(recovery),
        }],
    }
