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
    monkeypatch.setattr(pdfcheck, "poppler_pages", lambda _: ["i\u200ff", "", "ש"])
    monkeypatch.setattr(pdfcheck, "mupdf_pages", lambda _: ["fi", "", "X"])

    pages = pdfcheck.read_text_layer(Path("fixture.pdf"))["pages"]

    assert [p["pdfium_visual_chars"] for p in pages] == [2, 0, 1]
    assert pages[0]["readers"] == dict.fromkeys(("pdfminer", "poppler", "pymupdf"),
                                                {"chars": 2, "missing": 0, "extra": 0})
    assert pages[2]["readers"]["pdfminer"] == {"chars": 0, "missing": 1, "extra": 0}
    assert pages[2]["readers"]["poppler"] == {"chars": 1, "missing": 0, "extra": 0}
    assert pages[2]["readers"]["pymupdf"] == {"chars": 1, "missing": 1, "extra": 1}

    assert pages[0]["reader_order"] == {
        "pdfminer": "same_sequence", "poppler": "different_sequence", "pymupdf": "same_sequence",
    }
    assert pages[1]["reader_order"] == dict.fromkeys(("pdfminer", "poppler", "pymupdf"), "empty")
    assert pages[2]["reader_order"] == {
        "pdfminer": "different_inventory", "poppler": "same_sequence", "pymupdf": "different_inventory",
    }


def test_pilot_pdf_requires_matching_version_and_bytes(tmp_path):
    from hashlib import sha256

    from hdocsyngen.pilot_readback import _pdf_from_receipt

    path = tmp_path / "saved.pdf"
    path.write_bytes(b"invented PDF fixture")
    receipt = {"version": "fixture 2", "outputs": {
        "pdf": {"path": path.name, "sha256": sha256(path.read_bytes()).hexdigest()}
    }}
    assert _pdf_from_receipt(tmp_path, receipt, "fixture 2") == path
    with pytest.raises(ValueError, match="version"):
        _pdf_from_receipt(tmp_path, receipt, "fixture 3")
    path.write_bytes(b"changed fixture")
    with pytest.raises(ValueError, match="differs from the producer receipt"):
        _pdf_from_receipt(tmp_path, receipt, "fixture 2")


def test_pilot_pdf_checks_word_build_and_input(tmp_path):
    from hashlib import sha256

    from hdocsyngen.pilot_readback import _pdf_from_receipt
    from hdocsyngen.producers import VersionChanged, require_receipt_version

    path = tmp_path / "saved.pdf"
    path.write_bytes(b"invented PDF fixture")
    build = {"version": "fixture 2", "bundle_version": "fixture 2.1"}
    receipt = {**build, "input_sha256": "a" * 64, "outputs": {
        "pdf": {"path": path.name, "sha256": sha256(path.read_bytes()).hexdigest()}
    }}
    require_receipt_version("word", receipt, build)
    assert _pdf_from_receipt(tmp_path, receipt, "fixture 2", build=build, input_sha256="a" * 64) == path
    # A build update within the same marketing version must fail live and in readback.
    changed = {**receipt, "bundle_version": "fixture 2.2"}
    with pytest.raises(VersionChanged, match="producer build"):
        require_receipt_version("word", changed, build)
    with pytest.raises(ValueError, match="build"):
        _pdf_from_receipt(tmp_path, changed, "fixture 2", build=build)
    with pytest.raises(ValueError, match="input differs"):
        _pdf_from_receipt(tmp_path, receipt, "fixture 2", build=build, input_sha256="b" * 64)


def test_pilot_readback_checks_result_and_tree_before_parsing(tmp_path, monkeypatch):
    from hashlib import sha256
    import json
    from subprocess import CompletedProcess

    pytest.importorskip("pypdfium2")
    from hdocsyngen import pilot_readback

    monkeypatch.setattr(pilot_readback.subprocess, "run", lambda *_, **__: CompletedProcess([], 0))
    record = tmp_path / "fixture.result.json"
    tree = tmp_path / "fixture.tree.json"
    tree.write_bytes(b"changed source fixture")
    record.write_text(json.dumps({"sources": {"tree.json": "a" * 64}}))
    pin = {"word": {"version": "fixture 2", "bundle_version": "fixture 2.1"}}
    manifest = {"schema": "hdocsyngen_pilot.v0",
                "producer_builds": pin, "producer_builds_after": pin,
                "versions": {"word": "fixture 2"}, "versions_after": {"word": "fixture 2"},
                "docs": [{"doc_id": "fixture", "result": record.name, "result_sha256": "b" * 64}]}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Result record differs"):
        pilot_readback.run(tmp_path)
    manifest["docs"][0]["result_sha256"] = sha256(record.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Source tree differs"):
        pilot_readback.run(tmp_path)
