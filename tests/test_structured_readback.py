from copy import deepcopy

import pytest

from hdocsyngen.structured_readback import _readers, _structure


def test_structure_preserves_cells_and_binds_continuation_pages():
    def cell(r, c, text, paragraphs, **spans):
        return {"r": r, "c": c, "text": text, "paragraphs": paragraphs,
                "header": r == 0, "rowspan": 1, "colspan": 1} | spans

    table = {"id": "t1", "rows": 3, "cols": 2, "repeat_header": True, "cells": [
        cell(0, 0, "כותרת לדוגמה", ["h1"], colspan=2),
        cell(1, 0, "נוסח לדוגמה", ["r1"]),
        cell(1, 1, "", []),
        cell(2, 0, "פריט נוסף", ["r2"]),
        cell(2, 1, "81", ["r2-num"]),
    ]}
    gold = {"tables": [table], "forms": []}
    lines = [{"block_id": b, "page": p} for b, p in
             [("h1", 1), ("r1", 1), ("h1", 2), ("r2", 2), ("r2-num", 2)]]
    verified, = _structure(gold, lines)["tables"]
    assert verified["pages"] == [1, 2] and verified["page_breaks"] == [2]
    assert verified["cells"][0]["colspan"] == 2 and verified["cells"][2]["text"] == ""
    without_header = [line for line in lines if line != {"block_id": "h1", "page": 2}]
    with pytest.raises(ValueError, match="Header copy"):
        _structure(gold, without_header)
    with pytest.raises(ValueError, match="Body row split"):
        _structure(gold, lines + [{"block_id": "r2-num", "page": 1}])


def test_form_checkbox_keeps_value_and_projected_pages():
    field = {"id": "field-1", "type": "field", "kind": "checkbox",
             "slot": "box", "label": "אפשרות לדוגמה", "value": "unchecked", "paragraphs": ["para-1"]}
    gold = {"tables": [], "forms": [{"id": "form-1", "title": "טופס", "sections": [{"children": [field]}]}]}
    result = _structure(gold, [{"block_id": "para-1", "page": 2}])
    projected, = result["forms"][0]["sections"][0]["children"]
    assert projected["value"] == "unchecked" and projected["pages"] == [2]
    with pytest.raises(ValueError, match="Form field has no physical"):
        _structure(gold, [])


def test_reader_inventory_and_reversed_ltr_fail_separately():
    good = {"readers": {reader: {"missing": 0, "extra": 0} for reader in ("pdfminer", "poppler", "pymupdf")},
            "ltr_slots": {"reversed": 0}}
    _readers(good)
    missing = deepcopy(good)
    missing["readers"]["pymupdf"]["missing"] = 1
    with pytest.raises(ValueError, match="glyph inventory"):
        _readers(missing)
    backwards = good | {"ltr_slots": {"reversed": 1}}
    with pytest.raises(ValueError, match="reversed"):
        _readers(backwards)


def test_native_pilot_keeps_exact_source_bytes_and_declared_font(tmp_path):
    from hdocsyngen.fonts import FontFile, Registry
    from hdocsyngen.pilot import run_doc
    from hdocsyngen.tree import Document, Meta, Paragraph, Run, dumps

    tree = Document("fixture-1", Meta("report", "report", 1, font="Alef"),
                    [Paragraph("p1", [Run("נוסח לדוגמה")])])
    raw = (dumps(tree) + "\n").encode()
    coverage = frozenset(ord(char) for char in "נוסח לדוגמה")
    fonts = Registry([
        FontFile("alef.ttf", "Alef", "Regular", "Alef-Regular", "a" * 64, cmap=coverage),
        FontFile("heebo.ttf", "Heebo", "Regular", "Heebo-Regular", "b" * 64, cmap=coverage),
    ])
    result = run_doc("report", 1, None, fonts, tmp_path, {}, False, False,
                     source=tree, source_bytes=raw)
    assert result["font"] == "Alef"
    assert (tmp_path / "fixture-1" / "fixture-1.tree.json").read_bytes() == raw


def test_empty_docx_furniture_placeholder_preserves_the_source():
    from hdocsyngen.tree import Document, Furniture, Meta, Paragraph, Run
    from hdocsyngen.verify import verify_docx
    from hdocsyngen.writers.docx import write

    tree = Document("fixture-2", Meta("report", "report", 2),
                    [Paragraph("p1", [Run("נוסח לדוגמה")])])
    plain = write(tree)
    assert verify_docx(tree, plain) == []
    tree.furniture = Furniture(header=[Paragraph("h1", [Run("כותרת לדוגמה")])])
    with_header = write(tree)
    assert verify_docx(tree, plain) == ["header: text differs"]
    tree.furniture = Furniture()
    assert verify_docx(tree, with_header) == ["header: text differs"]
