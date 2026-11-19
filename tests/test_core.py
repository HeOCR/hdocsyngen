import io
import json
import random
import zipfile
from pathlib import Path

import pytest

from hdocsyngen import values as V
from hdocsyngen.cli import main
from hdocsyngen.gold import gold
from hdocsyngen.numbering import hebrew1, model_labels
from hdocsyngen.readers.docx_read import read
from hdocsyngen.templates import TEMPLATES, build
from hdocsyngen.textpool import TextPool
from hdocsyngen.tree import (AbstractNum, Document, Level, Meta, Num, NumRef, Paragraph, Run, dumps, loads,
                             validate)
from hdocsyngen.verify import verify_docx
from hdocsyngen.writers import docx

POOL = Path(__file__).parent / "data" / "invented_pool.jsonl"


@pytest.fixture(scope="module")
def pool():
    return TextPool.load(POOL)


def test_hebrew1():
    assert [hebrew1(n) for n in (1, 10, 11, 15, 16, 19, 20, 99, 100, 400, 515)] == \
        ["א", "י", "יא", "טו", "טז", "יט", "כ", "צט", "ק", "ת", "תקטו"]


def test_ids_fail_check_digit():
    rng = random.Random(3)
    for _ in range(500):
        s = V.fake_id(rng, company=rng.random() < 0.5)[0].text
        assert not V.is_valid_il_id(s)
    assert V.is_valid_il_id("000000018")          # a valid check digit, for the validator itself


def test_model_labels_restart_and_override():
    a = AbstractNum(1, [Level("decimal", "%1."), Level("decimal", "%1.%2."), Level("hebrew1", "(%3)")])
    nums = [Num(1, 1), Num(2, 1, {0: 5})]
    seq = [(1, 0), (1, 1), (1, 1), (1, 2), (1, 2), (1, 0), (1, 1), (2, 0), (2, 1)]
    body = [Paragraph(id=f"p{i}", runs=[Run("x")], num=NumRef(n, lvl)) for i, (n, lvl) in enumerate(seq)]
    doc = Document("d", Meta("t", "t", 0), body, abstract_nums=[a], nums=nums)
    labels = model_labels(doc)
    assert [labels[f"p{i}"] for i in range(len(seq))] == \
        ["1.", "1.1.", "1.2.", "(א)", "(ב)", "2.", "2.1.", "5.", "5.1."]


@pytest.mark.parametrize("template", TEMPLATES)
def test_templates_valid_and_roundtrip(pool, template):
    for seed in range(12):
        doc = build(template, f"{template}-{seed}", seed, pool)
        assert validate(doc) == []
        assert loads(dumps(doc)) == doc
        data = docx.write(doc)
        assert verify_docx(doc, data) == []
        assert docx.write(doc) == data                    # byte-reproducible
        g = gold(doc)
        assert g["reading_order"] and all(s["licence"] == "CC0-1.0" for s in g["text_sources"])


def test_tender_has_the_features(pool):
    docs = [build("tender", f"t{s}", s, pool) for s in range(20)]
    gs = [gold(d) for d in docs]
    assert all(g["tables"] and g["notes"] for g in gs)
    assert any(c["colspan"] > 1 for g in gs for t in g["tables"] for c in t["cells"])
    labels = [b.get("label_model", "") for g in gs for b in g["blocks"]]
    assert any(l.count(".") == 3 for l in labels) and any(l.startswith("(") for l in labels)
    kinds = {v["kind"] for g in gs for b in g["blocks"] for v in b.get("values", [])}
    assert {"amount", "date", "percent"} <= kinds


def test_verify_catches_damage(pool):
    doc = build("tender", "t-damage", 5, pool)
    data = docx.write(doc)
    z = zipfile.ZipFile(io.BytesIO(data))
    parts = {n: z.read(n) for n in z.namelist()}
    xml = parts["word/document.xml"].decode()
    first = doc.body[-1].runs[0].text                    # the signature line
    parts["word/document.xml"] = xml.replace(first, first[::-1], 1).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for n, b in parts.items():
            out.writestr(n, b)
    assert any("text differs" in p for p in verify_docx(doc, buf.getvalue()))


def test_reader_vmerge():
    from hdocsyngen.templates import Builder, table_from_rows
    b = Builder("d", 1, TextPool.load(POOL))
    t = table_from_rows(b, [["א", "ב", "ג"], ["1", "2", "3"], ["", "5", "6"]], merges={(1, 0): (2, 1), (0, 1): (1, 2)})
    doc = Document("d", Meta("t", "t", 0), [t])
    got = read(docx.write(doc))["blocks"][0]
    assert {(c["r"], c["c"], c["rowspan"], c["colspan"]) for c in got["cells"]} == \
        {(0, 0, 1, 1), (0, 1, 1, 2), (1, 0, 2, 1), (1, 1, 1, 1), (1, 2, 1, 1), (2, 1, 1, 1), (2, 2, 1, 1)}


def test_cli_build(tmp_path):
    assert main(["build", "--template", "report", "--seed", "40", "--count", "3", "--pool", str(POOL),
                 "--require-licence", "CC0-1.0", "--out", str(tmp_path)]) == 0
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert len(man["docs"]) == 3
    assert main(["verify-docx", str(tmp_path / "report-40.tree.json"), str(tmp_path / "report-40.docx")]) == 0
