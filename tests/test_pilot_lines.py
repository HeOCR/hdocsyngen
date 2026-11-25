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
