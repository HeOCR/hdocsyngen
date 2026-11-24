"""Export `hdoc_gold.v1` tables as `heocr_table.v1`, the grid format heocr-bench's table scorers read.

The mapping is exact: the same logical columns (0 = start column, rightmost in RTL), spans and cell text
(paragraphs joined by "\\n"). `header_rows` is the number of leading rows whose cells are all header cells.
`pages` is filled only when a producer layer gives the table's pages; `page_breaks` then gives the logical row
indices where each new page starts (0032 convention e, for the stitch measure).
"""
from __future__ import annotations


def header_rows(table: dict) -> int:
    rows = 0
    for r in range(table["rows"]):
        starting = [c for c in table["cells"] if c["r"] == r]
        covered = any(c["r"] < r < c["r"] + c["rowspan"] for c in table["cells"])
        if (starting or covered) and all(c["header"] for c in starting) and \
                all(c["header"] for c in table["cells"] if c["r"] < r < c["r"] + c["rowspan"]):
            rows = r + 1
        else:
            break
    return rows


def to_heocr_table(table: dict, pages: list[int] | None = None) -> dict:
    return {"schema": "heocr_table.v1", "id": table["id"], "rows": table["rows"], "cols": table["cols"],
            "header_rows": header_rows(table), "direction": "rtl", "pages": pages,
            "cells": [{"r": c["r"], "c": c["c"], "rowspan": c["rowspan"], "colspan": c["colspan"], "text": c["text"]}
                      for c in table["cells"]]}


def page_breaks(table: dict, producer_gold: dict) -> list[int] | None:
    """Logical row indices at which a new page starts (convention e), from a producer layer's cell pages.

    A row's page is the first page any of its starting cells' paragraphs land on. Returns None when the
    producer layer has no pages for the table's cells.
    """
    pages = {b["id"]: b["pages"] for b in producer_gold.get("blocks", []) if b.get("pages")}
    row_page = {}
    for c in table["cells"]:
        ps = [p for pid in c.get("paragraphs", []) for p in pages.get(pid, [])]
        if ps:
            row_page[c["r"]] = min(row_page.get(c["r"], ps[0]), min(ps))
    if not row_page:
        return None
    breaks, last = [], None
    for r in sorted(row_page):
        if last is not None and row_page[r] > last:
            breaks.append(r)
        last = row_page[r]
    return breaks


def export(gold: dict) -> list[dict]:
    """All tables of a gold document, in reading order."""
    return [to_heocr_table(t) for t in gold.get("tables", [])]
