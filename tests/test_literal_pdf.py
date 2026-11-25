import pytest

from hdocsyngen.literal_verify import _confirm, _verified_lines, source_pages
from hdocsyngen.pdfcheck import Glyph
from hdocsyngen.readers.literal_pdf import PaintedGlyph, position_index
from hdocsyngen.tree import Cell, Document, Meta, Paragraph, Run, Table


def _glyph(char, x=10):
    return Glyph(char, x, 19, x + 1, 21, (x, 20), None, "ABCDEF+OpenFace", 12, False)


def test_recovers_only_the_mismatching_slot_from_its_painted_glyph():
    row = [_glyph(")"), _glyph("[", 14)]
    visible = [PaintedGlyph("(", 27, (10.15, 20), "OpenFace"),
               PaintedGlyph("]", 34, (14, 20), "OpenFace")]
    got, witnesses = _confirm(row, {"(["}, position_index(visible), {"OpenFace": set("()[]")})
    assert got == "(["
    assert [(w["slot"], w["from"], w["to"]) for w in witnesses] == [(0, "U+0029", "U+0028")]


@pytest.mark.parametrize(
    ("witness", "candidate", "cmap"),
    [
        (PaintedGlyph("(", 0, (10, 20), "OpenFace"), "(", "()"),
        (PaintedGlyph("(", 27, (10, 20), "Fallback"), "(", "()"),
        (PaintedGlyph("(", 27, (11, 20), "OpenFace"), "(", "()"),
        (PaintedGlyph("(", 27, (10, 20), "OpenFace"), "(", ")"),
        (PaintedGlyph("}", 27, (10, 20), "OpenFace"), "}", "{}"),
        (PaintedGlyph("2", 27, (10, 20), "OpenFace"), "2", "12"),
        (None, "(", "()"),
    ],
)
def test_rejects_unwitnessed_unregistered_or_wrong_face_recovery(witness, candidate, cmap):
    raw = {"}": "{", "2": "1"}.get(candidate, ")")
    with pytest.raises(ValueError, match="unique literal match"):
        _confirm([_glyph(raw)], {candidate}, position_index([witness] if witness else []), {"OpenFace": set(cmap)})


def test_exact_readback_preserves_logical_ltr_token_and_rejects_reversal():
    pytest.importorskip("bidi")
    paragraph = Paragraph("p1", [Run("מדגם "), Run("21", "num")])
    correct = [_glyph(char, i) for i, char in enumerate("21םגדמ")]
    result = list(_verified_lines([correct], [paragraph], {}, {"OpenFace": set("21םגדמ")}))
    assert result[0]["text"] == "מדגם 21"
    assert result[0]["punctuation_glyph_witnesses"] == []
    wrong = [_glyph(char, i) for i, char in enumerate("12םגדמ")]
    with pytest.raises(ValueError, match="unique literal match"):
        list(_verified_lines([wrong], [paragraph], {}, {"OpenFace": set("21םגדמ")}))


def test_literal_flow_rejects_table_instead_of_guessing_its_reading_order():
    contents = Table("table", 1, 1, [Cell(0, 0, [Paragraph("cell", [Run("דוגמה")])])])
    doc = Document("example", Meta("report", "office", 1), [contents])
    with pytest.raises(ValueError, match="expects unnumbered text blocks"):
        source_pages(doc)


def test_actualtext_is_secondary_evidence_and_never_the_painted_witness(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    pytest.importorskip("pdfminer")
    from hdocsyngen.readers.literal_pdf import painted_pages, pdfminer_pages

    pdf = tmp_path / "marked.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), ")")
        xref, = page.get_contents()
        content = doc.xref_stream(xref)
        doc.update_stream(xref, b"/Span <</ActualText <FEFF0028>>> BDC\n" + content + b"\nEMC\n")
        doc.save(pdf)

    assert pdfminer_pages(pdf) == ["("]
    _, [painted] = painted_pages(pdf)
    assert [glyph.text for glyph in painted] == [")"]
    assert painted[0].glyph_id > 0
