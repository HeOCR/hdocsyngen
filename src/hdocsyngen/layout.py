"""Printed layout of a logical table (eval-approved schema addition, 2026-11-25).

A table with `blocks = k > 1` is printed "snaked": its body rows are cut into k consecutive runs of
`ceil(body_rows / k)` rows, printed side by side, each run under its own copy of the header rows. Block 0 is the
start block: the rightmost in an RTL table, so it occupies printed columns 0..cols-1 (columns are logical, start
first). The gold keeps the logical table (0032 convention a) plus `blocks_meta` with the boundaries.

Writers and the DOCX verifier both go through `printed()`, so a printed grid is checked against the same mapping the
gold is computed from. Header copies in blocks 1..k-1 reuse the header paragraphs (same ids, same twin colour).
"""
from __future__ import annotations

import math

from .tree import Cell, Table


def header_rows(t: Table) -> int:
    rows = 0
    for r in range(t.rows):
        if any(c.r == r for c in t.cells) and all(c.header for c in t.cells if c.r <= r < c.r + c.rowspan):
            rows = r + 1
        else:
            break
    return rows


def blocks_meta(t: Table) -> dict | None:
    """Block boundaries as logical body-row ranges [start, end) (rows counted in the logical table)."""
    if t.blocks <= 1:
        return None
    h = header_rows(t)
    per = math.ceil((t.rows - h) / t.blocks)
    return {"k": t.blocks, "header_rows": h, "rows_per_block": per,
            "ranges": [[h + i * per, min(t.rows, h + (i + 1) * per)] for i in range(t.blocks)]}


def printed(t: Table) -> Table:
    """The grid as printed. Identity for blocks == 1."""
    if t.blocks <= 1:
        return t
    m = blocks_meta(t)
    h, per, k = m["header_rows"], m["rows_per_block"], t.blocks
    cells: list[Cell] = []
    for cell in t.cells:
        if cell.r < h:
            for b in range(k):
                cells.append(Cell(r=cell.r, c=cell.c + b * t.cols, paragraphs=cell.paragraphs, rowspan=cell.rowspan,
                                  colspan=cell.colspan, header=True))
        else:
            b, off = divmod(cell.r - h, per)
            cells.append(Cell(r=h + off, c=cell.c + b * t.cols, paragraphs=cell.paragraphs, colspan=cell.colspan))
    rows = h + per
    covered = {(rr, cc) for c in cells for rr in range(c.r, c.r + c.rowspan) for cc in range(c.c, c.c + c.colspan)}
    for r in range(rows):                    # the last block may be short: pad with empty cells
        for c in range(t.cols * k):
            if (r, c) not in covered:
                cells.append(Cell(r=r, c=c, paragraphs=[]))
    widths = (t.col_widths or [1.0] * t.cols) * k
    return Table(id=t.id, rows=rows, cols=t.cols * k, cells=cells, ruled=t.ruled, repeat_header=t.repeat_header,
                 col_widths=widths)
