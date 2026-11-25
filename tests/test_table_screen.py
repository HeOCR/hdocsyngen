"""Generation-time digest-only table screening. All protected values are invented stand-ins."""
import hashlib
import json
import random
from pathlib import Path

import pytest

from hdocsyngen.pilot_filter import PilotFilter
from hdocsyngen.table_screen import _redraw_number, screen
from hdocsyngen.templates import Builder, table_from_rows
from hdocsyngen.textpool import TextPool
from hdocsyngen.tree import Document, Furniture, Run, Table, iter_paragraphs, text_of

POOL = Path(__file__).parent / "data" / "invented_pool.jsonl"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def guard_for(tmp_path, short=(), uni=()):
    normalizer = tmp_path / "fixture_normalizer.py"
    normalizer.write_text("fixture\n")
    keys = tmp_path / "ph1keys.py"
    keys.write_text(
        "from hashlib import sha256\nfrom types import SimpleNamespace\n"
        "N = SimpleNamespace(__file__=" + repr(str(normalizer)) + ")\n"
        "def H(text): return sha256(text.encode()).hexdigest()\n"
        "def words(text): return text.split()\n"
        "def key_short(text): return H(' '.join(words(text))) if 1 <= len(words(text)) <= 5 else None\n"
        "def key_uni(text): return H(' '.join(text.split())) if text.strip() else None\n"
    )
    manifest = {"schema": "hdocsyngen.pilot_projections.v1",
                "helpers": {"path": keys.name, "sha256": digest(keys.read_bytes())},
                "normalizer_sha256": digest(normalizer.read_bytes()), "layers": {}}
    for kind, texts in (("short_whole_line", short), ("unicode_whole_line", uni)):
        rows = sorted({digest(t.encode()) for t in texts} | {digest(b"placeholder " + kind.encode())})
        path = tmp_path / kind
        path.write_text("\n".join(rows) + "\n")
        manifest["layers"][kind] = {"path": path.name, "sha256": digest(path.read_bytes()), "rows": len(rows)}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return PilotFilter(path, digest(path.read_bytes()))


def matrix_doc(pool, names, values):
    b = Builder("screen", 1, pool)
    rows = [[names[0], names[0], ""], [names[1], values[0], names[1]], [names[2], values[1], values[2]]]
    table = table_from_rows(b, rows, header_rows=0, ruled="none")
    return Document("screen", b.meta("tables_dense", "tables"), [b.para([Run("כותרת בדויה לבדיקה")]), table],
                    furniture=Furniture(footer=[b.para([Run("1", "num", field="page")])]))


def texts(doc):
    return [text_of(p) for _, p in iter_paragraphs(doc)]


def test_hits_are_redrawn_and_repeated_names_stay_paired(tmp_path):
    pool = TextPool.load(POOL)
    guard = guard_for(tmp_path, short=("ערך", "12.5"), uni=("7",))
    doc = matrix_doc(pool, ["ערך", "שם", "כינוי"], ["12.5", "7", "33"])
    assert screen(doc, guard, pool, random.Random(3))
    after = texts(doc)
    assert not any(guard.hits(t) for t in after if t.strip())
    table = next(b for b in doc.body if isinstance(b, Table))
    cells = {(c.r, c.c): text_of(c.paragraphs[0]) for c in table.cells}
    assert cells[(0, 0)] == cells[(0, 1)] != "ערך"          # the name and its diagonal label changed together
    assert cells[(1, 0)] == cells[(1, 2)] == "שם"             # untouched names stay
    assert "." in cells[(1, 1)] and cells[(1, 1)] != "12.5"   # same shape, new value
    assert cells[(2, 2)] == "33"


def test_redrawn_numbers_keep_their_shape():
    rng = random.Random(0)
    for value in ("7", "42", "12.5", "3.25", "40.0", "12,345", "9.9%"):
        for _ in range(20):
            out = _redraw_number(value, rng)
            assert ("." in out) == ("." in value) and ("," in out) == ("," in value) and out.endswith("%") == value.endswith("%")
            if value.endswith((".0", ".5")) and len(value.split(".")[1]) == 1:
                assert out.endswith((".0", ".5"))


def test_an_unclearable_tree_is_rejected(tmp_path):
    pool = TextPool.load(POOL)
    guard = guard_for(tmp_path, uni=("כותרת בדויה לבדיקה 5",))
    doc = matrix_doc(pool, ["א", "ב", "ג"], ["1", "2", "3"])
    for _, p in iter_paragraphs(doc):
        if text_of(p) == "כותרת בדויה לבדיקה":
            p.runs = [Run("כותרת בדויה לבדיקה 5")]  # mixed letters and digits are never rewritten: drop the tree
    assert not screen(doc, guard, pool, random.Random(1))
