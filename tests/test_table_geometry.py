import pytest

from hdocsyngen.table_geometry import _table_gold, marker_css, markers
from hdocsyngen.templates import Builder, table_from_rows
from hdocsyngen.textpool import TextPool
from hdocsyngen.tree import Document


def make_table(rows, **options):
    builder = Builder("invented-tables", 32, TextPool([], {}))
    table = table_from_rows(builder, rows, **options)
    return Document(builder.doc_id, builder.meta("tables", "tables"), [table]), table


def page(number, cells):
    return {"page": number, "cells": [
        {"table_id": cell.table, "logical": cell.logical} for cell in cells
    ]}


def test_snake_maps_start_column_to_right_block_and_preserves_empty_padding():
    tree, table = make_table([["שם", "סך"], ["סוג א", "12"], ["סוג ב", "22"], ["סוג ג", ""]])
    table.blocks = 2
    physical = markers(tree)
    logical = {(m.cell.r, m.cell.c): m.logical for m in physical}
    assert logical[0, 0] == logical[0, 2] == (0, 0)
    assert logical[1, 0] == (1, 0)
    assert logical[1, 2] == (3, 0)
    assert logical[2, 2] is None
    assert len(set(marker_css(physical).values())) == len(physical)
    result, = _table_gold(tree, [page(1, physical)])
    assert result["direction"] == "rtl"
    assert result["blocks"]["ranges"] == [[1, 3], [3, 4]]
    assert result["cells"][-1]["text"] == ""


def test_continuation_counts_repeated_header_once_and_rejects_a_split_rowspan():
    tree, table = make_table(
        [["שם", "סך"], ["קטע", "20"], ["", "21"], ["יחידה", "23"]],
        merges={(1, 0): (2, 1)}, repeat_header=True,
    )
    physical = markers(tree)
    result, = _table_gold(tree, [
        page(1, [m for m in physical if m.cell.r < 3]),
        page(2, [m for m in physical if m.cell.r in (0, 3)]),
    ])
    assert result["pages"] == [1, 2]
    assert result["page_breaks"] == [3]
    assert result["header_rows"] == 1
    assert len(result["cells"]) == len(table.cells)
    with pytest.raises(ValueError, match="split or out-of-order body row"):
        _table_gold(tree, [
            page(1, [m for m in physical if m.cell.r < 2]),
            page(2, [m for m in physical if m.cell.r != 1]),
        ])
