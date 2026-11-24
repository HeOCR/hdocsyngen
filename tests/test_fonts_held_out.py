"""Fonts reserved for held-out print tests never reach a training render."""
import json
from types import SimpleNamespace

import pytest

from hdocsyngen import fonts as F


def _tiny_font(path, family):
    pytest.importorskip("fontTools")
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "alef"])
    fb.setupCharacterMap({0x05D0: "alef"})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0)); pen.lineTo((500, 0)); pen.lineTo((500, 500)); pen.closePath()
    fb.setupGlyf({".notdef": pen.glyph(), "alef": pen.glyph()})
    fb.setupHorizontalMetrics({".notdef": (600, 0), "alef": (600, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": "Regular", "psName": family.replace(" ", "") + "-Regular"})
    fb.setupOS2(); fb.setupPost(); fb.setupMaxp()
    fb.save(str(path))


def test_exclusion_list_is_the_shared_one():
    data = json.loads(F.EXCLUSION_PATH.read_text(encoding="utf-8"))
    assert data["schema"] == "heocr_font_exclusion.v1"
    assert F.HELD_OUT_FAMILIES == {
        "Drugulin CLM", "Simple CLM", "Aharoni CLM", "Ellinia CLM", "Keter YG", "Shofar", "Yehuda CLM",
    }
    assert len(F.HELD_OUT_SHA256) == 23
    assert all(len(s) == 64 for s in F.HELD_OUT_SHA256)


def test_scan_drops_held_out_families_unless_eval(tmp_path, monkeypatch):
    _tiny_font(tmp_path / "AharoniCLM-Book.ttf", "Aharoni CLM")
    _tiny_font(tmp_path / "Alef-Regular.ttf", "Alef")
    monkeypatch.delenv(F.EVAL_ENV, raising=False)
    assert F.Registry.scan([tmp_path]).families() == ["Alef"]
    monkeypatch.setenv(F.EVAL_ENV, "1")
    assert F.Registry.scan([tmp_path]).families() == ["Aharoni CLM", "Alef"]


def test_scan_drops_a_held_out_file_by_sha256(tmp_path, monkeypatch):
    _tiny_font(tmp_path / "Renamed.ttf", "Alef")
    real = F.hashlib.sha256((tmp_path / "Renamed.ttf").read_bytes()).hexdigest()
    monkeypatch.delenv(F.EVAL_ENV, raising=False)
    monkeypatch.setattr(F, "HELD_OUT_SHA256", frozenset({real}))
    assert F.Registry.scan([tmp_path]).families() == []


def test_fit_font_refuses_a_requested_held_out_family(monkeypatch):
    monkeypatch.delenv(F.EVAL_ENV, raising=False)
    with pytest.raises(F.HeldOutFontError):
        F.fit_font(SimpleNamespace(doc_id="d1"), F.Registry([]), None, prefer=["Drugulin CLM", "Alef"])
