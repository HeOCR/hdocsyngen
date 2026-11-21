from pathlib import Path

import pytest

from hdocsyngen import pdfcheck
from hdocsyngen.tree import Document, Meta, Paragraph, Run, twin_colours


def glyph(text, x, y, rgb=None):
    return pdfcheck.Glyph(text, x, y, x + 1, y + 1, (x, y), rgb, "fixture", 10, False)


def test_visual_order_uses_slots_for_rtl_and_ltr():
    # Deliberately interleave producer stream order, baselines and positions.
    chars = [glyph("א", 9, 50), glyph("Z", 2, 30), glyph("2", 3, 50), glyph("ב", 8, 49.7), glyph("1", 2, 50)]
    assert pdfcheck._visual_lines(chars) == ["12בא", "Z"]


def test_ltr_slots_find_reversal_within_its_own_block(monkeypatch):
    monkeypatch.setattr(pdfcheck, "_bidi_order", lambda runs, line: None)
    doc = Document(doc_id="test", meta=Meta(template="tender", look="tender", seed=0), body=[
        Paragraph("english", [Run("אב "), Run("AB12", "en"), Run(" גד")]),
        Paragraph("amount", [Run("סכום "), Run("12,340", "num")]),
        Paragraph("unresolved", [Run("XY34", "en")]),
    ])
    colours = twin_colours(doc)
    glyphs = [(1, glyph(c, x, 50, colours["english"])) for x, c in enumerate("AB12בא")]
    glyphs += [(1, glyph(c, x + 10, 50, colours["amount"])) for x, c in enumerate("043,21")]
    # A correct token elsewhere on the same baseline must not mask the reversal or the missing token.
    glyphs += [(1, glyph(c, x + 20, 50, colours["english"])) for x, c in enumerate("12,340 XY34")]
    assert pdfcheck._ltr_slots(doc, glyphs[::-1]) == {
        "english": {"forward": 1, "reversed": 0, "unresolved": 0},
        "amount": {"forward": 0, "reversed": 1, "unresolved": 0},
        "unresolved": {"forward": 0, "reversed": 0, "unresolved": 1},
    }


def test_full_visual_line_keeps_ltr_and_rtl_orders():
    pytest.importorskip("bidi")
    runs = [Run("אב "), Run("12,340 AB12", "en"), Run(" גד")]
    assert pdfcheck._bidi_order(runs, "דג 12,340 AB12 בא") == {"python_bidi": True, "rust_bidi": True}
    assert pdfcheck._bidi_order(runs, "דג 043,21 AB12 בא") == {"python_bidi": False, "rust_bidi": False}
    assert pdfcheck._bidi_order(runs, "דג AB12 בא") is None


def test_readers_are_compared_per_page_even_with_an_empty_page(monkeypatch):
    monkeypatch.setattr(pdfcheck, "_chars", lambda _: [(1, glyph("ﬁ", 2, 50)), (3, glyph("ש", 2, 50))])
    monkeypatch.setattr(pdfcheck, "_stream_chars", lambda _: [(1, glyph("f", 2, 50)), (1, glyph("i", 3, 50))])
    monkeypatch.setattr(pdfcheck, "poppler_pages", lambda _: ["f\u200fi", "", "ש"])
    monkeypatch.setattr(pdfcheck, "mupdf_pages", lambda _: ["fi", "", "X"])

    pages = pdfcheck.read_text_layer(Path("fixture.pdf"))["pages"]

    assert [p["pdfium_visual_chars"] for p in pages] == [2, 0, 1]
    assert pages[0]["readers"] == dict.fromkeys(("pdfminer", "poppler", "pymupdf"),
                                                {"chars": 2, "missing": 0, "extra": 0})
    assert pages[2]["readers"]["pdfminer"] == {"chars": 0, "missing": 1, "extra": 0}
    assert pages[2]["readers"]["poppler"] == {"chars": 1, "missing": 0, "extra": 0}
    assert pages[2]["readers"]["pymupdf"] == {"chars": 1, "missing": 1, "extra": 1}
