import re
from pathlib import Path

import pytest

from hdocsyngen.form_export import export
from hdocsyngen.gold import gold
from hdocsyngen.templates import build
from hdocsyngen.templates import forms as F
from hdocsyngen.textpool import TextPool
from hdocsyngen.tree import dumps, form_fields, iter_paragraphs, loads, text_of, validate
from hdocsyngen.values import is_valid_il_id
from hdocsyngen.verify import verify_docx
from hdocsyngen.writers import docx, html

POOL = Path(__file__).parent / "data" / "invented_pool.jsonl"
SEEDS = range(25)


@pytest.fixture(scope="module")
def pool():
    return TextPool.load(POOL)


@pytest.fixture(scope="module")
def docs(pool):
    return [build("forms", f"form-{s}", s, pool) for s in SEEDS]


def _fields(doc):
    return [f for form in doc.forms for s in form["sections"] for f in form_fields(s["children"])]


def test_forms_are_valid_round_trip_and_survive_the_writers(docs):
    for doc in docs:
        assert validate(doc) == []
        assert loads(dumps(doc)).forms == doc.forms
        assert verify_docx(doc, docx.write(doc)) == []
        assert html.write(doc)


def test_every_field_is_printed_as_its_gold_says(docs):
    for doc in docs:
        texts = {p.id: text_of(p) for _, p in iter_paragraphs(doc)}
        for f in _fields(doc):
            printed = "\n".join(texts[p] for p in f["paragraphs"])
            if f["kind"] == "checkbox":
                mark = "X" if f["value"] == "checked" else " "
                assert re.search(r"[\[(]" + mark + r"[\])] " + re.escape(f["label"]), printed)
            elif f["kind"] == "choice":
                assert printed.startswith(f["label"] + ":")
                if f["value"]:
                    assert re.search(r"[\[(]X[\])] " + re.escape(f["value"]), printed)
                else:
                    assert "X" not in printed
            else:
                assert f["label"] in printed
                if f["value"]:
                    assert f["value"] in printed
                elif f["slot"] == "line":
                    assert F.BLANK in printed


def test_values_are_fictional_and_some_fields_are_blank(docs):
    fields = [f for doc in docs for f in _fields(doc)]
    kinds = {f["kind"] for f in fields}
    assert {"text", "number", "date", "checkbox", "choice", "signature"} <= kinds
    assert {f["slot"] for f in fields} == {"line", "box", "cell"}
    blank = sum(1 for f in fields if f["value"] == "" and f["kind"] != "signature")
    assert 0.05 < blank / len(fields) < 0.4
    for f in fields:
        assert not any(is_valid_il_id(d) for d in re.findall(r"\d[\d-]{7,10}\d", f["value"]))
        if f["label"] == "שם מלא" and f["value"]:
            assert f["value"] in F.SAMPLE_NAMES
        if f["kind"] == "signature":
            assert f["value"] == ""


def test_export_is_hdoc_form_v1_with_tables_groups_and_pages(pool, docs):
    seen = set()
    for doc in docs:
        g = gold(doc, dumps(doc))
        (form,) = export(g)
        assert form["schema"] == "hdoc_form.v1" and form["direction"] == "rtl"
        assert all(s["type"] == "section" and s["pages"] is None for s in form["sections"])

        def walk(children):
            for ch in children:
                seen.add(ch["type"])
                assert "paragraphs" not in ch
                if ch["type"] == "table":
                    assert ch["table"]["schema"] == "heocr_table.v1"
                if ch["type"] == "group":
                    assert ch["columns"] == 2 and ch["children"]
                    walk(ch["children"])
        for s in form["sections"]:
            walk(s["children"])
    assert seen == {"field", "table", "group"}
    # With a producer layer, pages come from the paragraphs that print each field.
    doc = docs[0]
    g = gold(doc, dumps(doc))
    producer = {"blocks": [{"id": b["id"], "pages": [1 if i < len(g["blocks"]) // 2 else 2]}
                           for i, b in enumerate(g["blocks"])]}
    (form,) = export(g, producer)
    fields = [ch for s in form["sections"] for ch in s["children"] if ch["type"] == "field"]
    assert all(f["pages"] in ([1], [2], [1, 2]) for f in fields)
    assert form["sections"][0]["pages"][0] == 1


def _bench_fields(form):
    """heocr-bench forms.fields() (src/heocr_bench/forms.py @ 910fd566), copied in spirit: the scorer's walk over
    section children, groups and nested sections through `children` only."""
    out = []

    def walk(children):
        for ch in children:
            kind = ch.get("type")
            if kind == "field":
                out.append(ch)
            elif kind in ("group", "section"):
                walk(ch.get("children", []))
    for section in form.get("sections", []):
        walk(section.get("children", []))
    return out


def test_the_scorer_sees_every_field_of_the_tree(docs):
    grouped = 0
    for doc in docs:
        (form,) = export(gold(doc, dumps(doc)))
        assert [f["id"] for f in _bench_fields(form)] == [f["id"] for f in _fields(doc)]
        grouped += sum(1 for s in form["sections"] for ch in s["children"] if ch["type"] == "group")
    assert grouped >= 1


def test_labels_are_not_repeated_within_a_form(docs):
    for doc in docs:
        labels = [(f["label"], f["kind"]) for f in _fields(doc) if f["kind"] not in ("signature", "date", "choice")]
        assert len(labels) == len(set(labels))


def test_a_form_is_deterministic_per_seed(pool):
    assert dumps(build("forms", "x", 3, pool)) == dumps(build("forms", "x", 3, pool))
