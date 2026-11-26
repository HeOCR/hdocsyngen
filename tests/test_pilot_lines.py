import pytest

from hdocsyngen.pdfcheck import Glyph
from hdocsyngen.pilot_lines import _parts
from hdocsyngen.tree import Paragraph, Run


def row(visual, y):
    return [Glyph(char, x, y, x + 1, y + 2, (x, y), (0, 0, 1), "Fixture", 10, False)
            for x, char in enumerate(visual) if not char.isspace()]


def test_wrapped_source_lines_preserve_order_and_offsets():
    pytest.importorskip("bidi")
    block = Paragraph("p1", [Run("ענן רך ירד")])
    result = _parts([(1, row("ךר ןנע", 100)), (2, row("דרי", 300))], block, "")
    assert [(line.page, line.body, line.source_span) for line in result] == [
        (1, "ענן רך", (0, 6)), (2, "ירד", (7, 10))
    ]


def test_same_character_inventory_wrong_positions_is_held():
    pytest.importorskip("bidi")
    block = Paragraph("p1", [Run("ענן רך")])
    with pytest.raises(ValueError, match="physical glyphs differ"):
        _parts([(1, row("ענן רך", 100))], block, "")


def test_side_by_side_headers_verify_both_copies_and_order_ltr():
    from dataclasses import replace

    from hdocsyngen.pilot_lines import _table_parts
    from hdocsyngen.tree import Cell, Table

    pytest.importorskip("bidi")
    block = Paragraph("p1", [Run("728", "num")])
    cell = Cell(r=0, c=0, header=True, paragraphs=[block])
    table = Table("t1", rows=5, cols=2, cells=[cell], blocks=2)
    layout = {"header_rows": 1, "rows_per_block": 2}

    def shifted(text, x):
        return [replace(g, origin=(g.origin[0] + x, 100)) for g in row(text, 100)]

    exact = shifted("728", 370) + shifted("728", 130)
    lines = _table_parts(block, {1: exact}, {1: 600}, table, cell, layout)
    assert [(line.table_panel, line.body) for line in lines] == [(0, "728"), (1, "728")]
    with pytest.raises(ValueError, match="Missing or misplaced"):
        _table_parts(block, {1: exact[:3]}, {1: 600}, table, cell, layout)
    wrong = shifted("827", 370) + shifted("728", 130)
    with pytest.raises(ValueError, match="physical glyphs differ"):
        _table_parts(block, {1: wrong}, {1: 600}, table, cell, layout)


def test_bare_word_counter_requires_unique_expected_digits_in_margin():
    from hdocsyngen.pilot_lines import _recover_bare_field

    footer, body = row("12", 31), row("12", 210)
    assert _recover_bare_field(body + footer, "12", "footer", 842, "f1") == footer
    with pytest.raises(ValueError, match="counter"):
        _recover_bare_field(body, "12", "footer", 842, "f1")
    with pytest.raises(ValueError, match="counter"):
        _recover_bare_field(footer + row("12", 20), "12", "footer", 842, "f1")
