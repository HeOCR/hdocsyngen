"""Layer faults (PR 3). Pure transforms always; the PDF round trip only where Ghostscript, the faults extra and an
open Hebrew font (HDOCSYNGEN_LAYER_FONT) are present. Invented text only."""
import os
import random
import shutil
from pathlib import Path

import pytest

from hdocsyngen import layer_faults as LF
from hdocsyngen.layer_faults import Char, Line


def word(text, x_right, y=100.0, w=5.0, k0=0, rtl=True):
    """Characters of ``text`` in logical order; Hebrew laid out right to left from ``x_right``."""
    out = []
    for i, ch in enumerate(text):
        x1 = x_right - i * w if rtl else x_right + (i + 1) * w
        out.append(Char(ch, x1 - w, y, x1, y + 10.0, k=k0 + i))
    return out


def test_lines_keep_the_producer_order_and_split_by_height():
    a = word("אבג", 200.0)
    b = word("12.5", 50.0, rtl=False, k0=3)
    c = word("דה", 200.0, y=70.0, k0=7)
    lines = LF.lines_from_chars(c + a + b)  # stream order mixed up on purpose
    assert ["".join(ch.text for ch in line.chars) for line in lines] == ["אבג12.5", "דה"]


def test_visual_order_mirrors_hebrew_words_only():
    line = Line(word("שלום", 200.0) + [Char(" ", 175.0, 100.0, 180.0, 110.0)] + word("12", 100.0, rtl=False))
    before = [(c.text, c.x0) for c in line.chars]
    assert LF.visual_order([line]) == 1
    hebrew = [(c.text, c.x0) for c in line.chars[:4]]
    assert [t for t, _ in hebrew] == list("שלום")
    assert [x for _, x in hebrew] == [x for _, x in before[:4]][::-1]   # the letters sit at mirrored places
    assert [(c.text, c.x0) for c in line.chars[5:]] == before[5:]          # digits keep theirs


def test_split_runs_moves_the_rest_of_a_word_and_is_seeded():
    def run(seed):
        line = Line(word("מילהארוכה", 200.0))
        n = LF.split_runs([line], random.Random(seed), share=1.0)
        return n, [c.shift for c in line.chars]
    n, shifts = run(1)
    assert n == 1
    cut = next(i for i, s in enumerate(shifts) if s)
    assert cut >= 1 and all(s == 0 for s in shifts[:cut]) and all(s > 0 for s in shifts[cut:])
    assert run(1) == (n, shifts)


def test_drop_dots_only_between_digits():
    line = Line(word("3.25", 50.0, rtl=False) + word("סוף.", 200.0, k0=10))
    assert LF.drop_dots([line]) == 1
    assert "".join(c.text for c in line.chars) == "325סוף."


def test_apply_records_each_fault_and_rejects_unknown_ones():
    lines = [Line(word("אבג", 200.0) + word("1.5", 50.0, rtl=False, k0=3))]
    rec = LF.apply(lines, ["drop_dots", "visual_order", "hidden_ocr"], seed=4)
    assert rec["drop_dots"] == 1 and rec["visual_order"] == 1
    assert set(rec["hidden_ocr"]) == {"dx", "dy"} and all(abs(v) <= 1.5 for v in rec["hidden_ocr"].values())
    with pytest.raises(ValueError):
        LF.apply(lines, ["nope"], seed=0)


FONT = os.environ.get("HDOCSYNGEN_LAYER_FONT")


@pytest.mark.skipif(not (FONT and shutil.which("gs")), reason="needs Ghostscript and HDOCSYNGEN_LAYER_FONT")
def test_a_faulted_pdf_looks_the_same_and_reads_as_faulted(tmp_path):
    pytest.importorskip("reportlab")
    pytest.importorskip("pypdf")
    pdfium = pytest.importorskip("pypdfium2")
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    src = tmp_path / "producer.pdf"
    pdfmetrics.registerFont(TTFont("Src", FONT))
    c = canvas.Canvas(str(src), pageSize=(300, 200))
    c.setFont("Src", 14)
    c.drawRightString(280, 150, "סכום כולל")
    c.drawString(40, 150, "12.50")
    c.save()

    out = tmp_path / "faulted.pdf"
    meta = LF.fault_pdf(src, out, Path(FONT), ["visual_order", "drop_dots"], seed=1)
    assert meta["pages"][0]["visual_order"] >= 1 and meta["pages"][0]["drop_dots"] == 1
    (page,) = LF.check(src, out)
    assert page["pixels_changed_pct"] < 2.0
    assert page["chars_missing"] == {".": 1} and page["chars_extra"] == {}
    plain = tmp_path / "plain.pdf"
    LF.fault_pdf(src, plain, Path(FONT), [], seed=1)  # the same rebuild with no fault
    read = lambda f: pdfium.PdfDocument(str(f))[0].get_textpage().get_text_range().split()
    clean, faulted = read(plain), read(out)
    hebrew = [w for w in clean if any("\u05d0" <= ch <= "\u05ea" for ch in w)]
    assert hebrew and all(w[::-1] in faulted for w in hebrew)   # each word reads backwards
    assert "12.50" in clean and not any("." in w for w in faulted)
    assert (tmp_path / "faulted.pdf.faults.json").exists()
