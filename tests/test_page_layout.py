import pytest

from hdocsyngen.layout_record import image_record
from hdocsyngen.page_verify import _layout_rows, body_columns
from hdocsyngen.pdfcheck import Glyph
from hdocsyngen.tree import Document, Heading, Meta, Paragraph, Run


def test_explicit_native_column_anchor_holds_rtl_source_order():
    right = Heading("right", 1, [Run("כתבה")])
    item = Paragraph("entry", [Run("רישום")])
    left = Heading("left", 2, [Run("המשך")])
    tree = Document("example", Meta("article", "office", 1, columns=2), [right, item, left])
    assert body_columns(tree, "left") == [[right, item], [left]]
    with pytest.raises(ValueError, match="second-column anchor"):
        body_columns(tree, "right")


def test_raised_note_marker_uses_painted_box_height_when_quartz_reports_unit_size():
    marker = Glyph("1", 21, 77, 23, 82, (21, 77), None, "OpenFace", 1, False)
    body = Glyph("א", 24, 72, 33, 81, (24, 72), None, "OpenFace", 1, False)
    assert _layout_rows([body, marker]) == [[marker, body]]


def test_ground_truth_uses_media_dpi_and_preserves_rtl_order():
    def region(name, side):
        return {"kind": "text", "role": "body", "source_id": name, "text": name,
                "half": side, "lines": [{"text": name}]}

    regions = [region("ימין", "right"), region("שמאל", "left")]
    projections = {"b0-l0": [[120, 20], [160, 21], [159, 42], [120, 41]],
                   "b1-l0": [[20, 30], [50, 30], [50, 50], [20, 50]]}
    result = image_record({"regions": regions}, projections, image_sha256="a"*64, image_bytes=10,
                          image_size=(200, 150), dpi=144, image_format="png", producer_version="test",
                          producer="chrome", capture="scan", native_pdf_sha256="b"*64)
    assert result["pages"][0]["width"] == 100
    assert [b["half"] for b in result["blocks"]] == ["right", "left"]
    assert result["blocks"][0]["bbox"] == [60, 10, 80, 21]
    assert result["blocks"][0]["lines"][0]["polygon_px"] == projections["b0-l0"]
