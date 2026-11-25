"""Bind observed Chrome cell geometry to a source tree's logical RTL tables."""

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from .fonts import FontFile
from .gold import gold
from .layout import blocks_meta, printed
from .literal_verify import _verified_lines, _visual_rows, declared_glyphs
from .pdfcheck import _chars
from .readers.literal_pdf import painted_pages, position_index
from .table_export import to_heocr_table
from .tree import Cell, Document, Table, dumps, validate


@dataclass(frozen=True)
class CellMarker:
    table: str
    cell: Cell
    logical: tuple[int, int] | None
    colour: tuple[int, int, int]

    @property
    def key(self):
        return self.table, self.cell.r, self.cell.c


def markers(tree: Document) -> tuple[CellMarker, ...]:
    """Every printed cell has a marker, including padding and empty cells."""
    result = []
    for table in (block for block in tree.body if isinstance(block, Table)):
        plan = blocks_meta(table)
        for cell in sorted(printed(table).cells, key=lambda cell: (cell.r, cell.c)):
            logical = cell.r, cell.c
            if plan:
                block, col = divmod(cell.c, table.cols)
                row = cell.r
                if row >= plan["header_rows"]:
                    row += block * plan["rows_per_block"]
                logical = (row, col) if row < table.rows else None
            ordinal = 1 + len(result)
            if ordinal > 0xFFFF:
                raise ValueError("Document has too many printed cells for the geometry twin")
            result.append(CellMarker(table.id, cell, logical, (ordinal >> 8, ordinal & 255, 173)))
    return tuple(result)


def marker_css(markers: tuple[CellMarker, ...]) -> dict[tuple[str, int, int], str]:
    return {marker.key: "#%02x%02x%02x" % marker.colour for marker in markers}


def _trace(page):
    return [(span["font"], span["size"], span["chars"]) for span in page.get_texttrace()
            if span["type"] in (0, 1) and span["opacity"] > 0]


def _visible_boxes(page, marker_by_colour):
    seen = set()
    for drawing in page.get_drawings():
        if drawing["fill"] is None:
            continue
        colour = tuple(round(channel * 255) for channel in drawing["fill"])
        if colour not in marker_by_colour:
            continue
        if len(drawing["items"]) != 1 or drawing["items"][0][0] != "re":
            raise ValueError("Cell paint is not one rectangle")
        marker = marker_by_colour[colour]
        box = drawing["rect"]
        if marker.key in seen or not box in page.rect or box.is_empty:
            raise ValueError(f"Invalid or repeated geometry for printed cell {marker.key}")
        seen.add(marker.key)
        yield marker, tuple(box)


def _cell_lines(cells, glyphs, page_height, painted, declared):
    assigned = [[] for _ in cells]
    for glyph in glyphs:
        x = (glyph.x0 + glyph.x1) / 2
        y = page_height - glyph.origin[1]
        owners = [i for i, (_, (left, top, right, bottom)) in enumerate(cells)
                  if left <= x < right and top <= y < bottom]
        if len(owners) > 1:
            raise ValueError("A PDF glyph occupies two printed cells")
        if owners:
            assigned[owners[0]].append(glyph)
    for (marker, _), glyphs_in_cell in zip(cells, assigned, strict=True):
        try:
            yield list(_verified_lines(_visual_rows(glyphs_in_cell), marker.cell.paragraphs, painted, declared))
        except ValueError as error:
            raise ValueError(f"Printed cell {marker.key}: {error}") from error


def _table_gold(tree, printed_pages):
    result = []
    for logical in gold(tree)["tables"]:
        table = logical["id"]
        locations = defaultdict(set)
        for page in printed_pages:
            for cell in page["cells"]:
                if cell["table_id"] == table and cell["logical"] is not None:
                    locations[tuple(cell["logical"])].add(page["page"])
        expected = {(c["r"], c["c"]) for c in logical["cells"]}
        if set(locations) != expected:
            raise ValueError(f"Logical table {table} lacks observed cells")
        pages = sorted(set().union(*locations.values()))
        if pages != list(range(pages[0], pages[-1] + 1)):
            raise ValueError(f"Logical table {table} has nonconsecutive pages")
        canonical = to_heocr_table(logical, [pages[0], pages[-1]])
        header_rows = canonical["header_rows"]
        row_pages = defaultdict(set)
        for cell in logical["cells"]:
            for row in range(max(header_rows, cell["r"]), cell["r"] + cell["rowspan"]):
                row_pages[row].update(locations[(cell["r"], cell["c"])])
        body = sorted((row, min(where)) for row, where in row_pages.items())
        body_pages = [page for _, page in body]
        if (any(len(where) != 1 for where in row_pages.values()) or body_pages != sorted(body_pages)
                or (body and set(body_pages) != set(pages))):
            raise ValueError(f"Logical table {table} has a split or out-of-order body row")
        canonical["page_breaks"] = [row for (_, before), (row, after) in zip(body, body[1:]) if before != after]
        result.append(canonical)
    return result


def observe(pdf: Path, twin: Path, tree: Document, faces: tuple[FontFile, ...]) -> dict:
    """Require position-identical twin glyphs and literal readback inside each cell."""
    import pymupdf

    cells = markers(tree)
    if not cells:
        raise ValueError("Table geometry requires at least one source table")
    by_colour = {marker.colour: marker for marker in cells}
    declared = declared_glyphs(tree.meta.font, faces)
    _, painted = painted_pages(pdf)
    glyphs = defaultdict(list)
    for page, glyph in _chars(pdf):
        if not glyph.text.isspace():
            glyphs[page].append(glyph)
    observed, checked_keys = [], set()
    with pymupdf.open(pdf) as native, pymupdf.open(twin) as geometry:
        if len(native) != len(geometry):
            raise ValueError("The native PDF and geometry twin paginated differently")
        for index, (page, twin_page) in enumerate(zip(native, geometry, strict=True)):
            if page.rect != twin_page.rect or _trace(page) != _trace(twin_page):
                raise ValueError("The geometry twin changed the printed text or its position")
            boxes = list(_visible_boxes(twin_page, by_colour))
            lines = _cell_lines(boxes, glyphs[index + 1], page.rect.height, position_index(painted[index]), declared)
            rows = []
            for (marker, box), verified in zip(boxes, lines, strict=True):
                checked_keys.add(marker.key)
                rows.append({
                    "table_id": marker.table,
                    "logical": list(marker.logical) if marker.logical is not None else None,
                    "printed": [marker.cell.r, marker.cell.c],
                    "span": [marker.cell.rowspan, marker.cell.colspan],
                    "header": marker.cell.header,
                    "bbox_pt": list(box),
                    "lines": verified,
                })
            rows.sort(key=lambda row: (row["bbox_pt"][1], -row["bbox_pt"][2]))
            observed.append({"page": index + 1, "size_pt": list(page.rect.br), "cells": rows})
    if checked_keys != {marker.key for marker in cells}:
        raise ValueError("The geometry twin did not paint every printed cell")
    return {"tables": _table_gold(tree, observed), "pages": observed}


def render(tree: Document, faces: tuple[FontFile, ...], output: Path) -> dict:
    """Write the native PDF and observe its printed cells with a disposable geometry twin."""
    from .producers import chrome_convert
    from .writers.html import write

    if problems := validate(tree):
        raise ValueError(f"Invalid input tree: {problems[0]}")
    if not markers(tree):
        raise ValueError("Table geometry requires at least one source table")
    declared_glyphs(tree.meta.font, faces)
    output.mkdir(exist_ok=False, parents=True)
    with TemporaryDirectory(prefix=".table-geometry-", dir=output.parent) as directory:
        scratch = Path(directory)
        native_html, twin_html = scratch / "native.html", scratch / "geometry.html"
        native_html.write_bytes(write(tree, embedded_fonts=faces))
        twin_html.write_bytes(write(tree, embedded_fonts=faces, cell_colours=marker_css(markers(tree))))
        native = chrome_convert(native_html, scratch)
        twin = chrome_convert(twin_html, scratch)
        if native["version"] != twin["version"]:
            raise ValueError("Chrome changed version between the native PDF and its geometry twin")
        pdf = scratch / native["outputs"]["pdf"]["path"]
        marked = scratch / twin["outputs"]["pdf"]["path"]
        observed = observe(pdf, marked, tree, faces)
        pdf.replace(output / "native.pdf")
    native["outputs"]["pdf"]["path"] = "native.pdf"
    return {
        "doc_id": tree.doc_id,
        "tree_sha256": sha256(dumps(tree).encode()).hexdigest(),
        "producer": native,
        "geometry_twin_sha256": twin["outputs"]["pdf"]["sha256"],
        "fonts": [{"family": face.family, "postscript": face.postscript, "sha256": face.sha256} for face in faces],
        **observed,
    }
