import re
from pathlib import Path

import pytest

from hdocsyngen.labels import producer_labels
from hdocsyngen.numbering import model_labels
from hdocsyngen.templates import TEMPLATES, build
from hdocsyngen.textpool import TextPool
from hdocsyngen.tree import colour_index, twin_colours
from hdocsyngen.writers import docx, html
from hdocsyngen.verify import verify_docx

POOL = Path(__file__).parent / "data" / "invented_pool.jsonl"


@pytest.fixture(scope="module")
def pool():
    return TextPool.load(POOL)


def test_twin_colours_unique_and_near_black(pool):
    doc = build("tender", "t", 1, pool)
    cols = twin_colours(doc)
    assert len(set(cols.values())) == len(cols)
    assert all(max(c) <= 31 and colour_index(c) > 0 for c in cols.values())


@pytest.mark.parametrize("template", TEMPLATES)
def test_twin_docx_carries_the_same_gold(pool, template):
    doc = build(template, "d", 4, pool)
    twin = docx.write(doc, twin=True)
    assert verify_docx(doc, twin) == []
    assert twin != docx.write(doc)


@pytest.mark.parametrize("template", TEMPLATES)
def test_html_has_every_block_and_counter(pool, template):
    doc = build(template, "d", 2, pool)
    h = html.write(doc, twin=True).decode()
    for b in doc.body:
        if hasattr(b, "runs") or b.type == "table":
            assert f'id="{b.id}"' in h
    assert "counter-reset" in h and "counter(page)" in h
    assert len(re.findall(r'class="nref"', h)) == len(doc.notes)
    assert re.search(r"color: rgb\(\d+,\d+,\d+\)", h)


def test_producer_labels_by_order(pool):
    doc = build("tender", "d", 9, pool)
    model = model_labels(doc)
    from hdocsyngen.tree import text_of
    lines = []
    for b in doc.body:
        if hasattr(b, "runs"):
            lab = model.get(b.id, "")
            lines.append(f"{lab}\t{text_of(b)}" if lab else text_of(b))
    labels, unmatched = producer_labels(doc, lines)
    assert unmatched == []
    assert all(labels[k] == v.strip() for k, v in model.items() if k in labels)
    assert len(labels) == sum(1 for b in doc.body if getattr(b, "num", None) is not None)
