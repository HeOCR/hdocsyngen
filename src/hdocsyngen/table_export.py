"""Export `hdoc_gold.v1` tables as `heocr_table.v1`, the grid format heocr-bench's table scorers read.

The mapping is exact: the same logical columns (0 = start column, rightmost in RTL), spans and cell text
(paragraphs joined by "\\n"). `header_rows` is the number of leading rows whose cells are all header cells.
`pages` is filled only when a producer layer gives the table's pages.
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


def export(gold: dict) -> list[dict]:
    """All tables of a gold document, in reading order."""
    return [to_heocr_table(t) for t in gold.get("tables", [])]
