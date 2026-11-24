from pathlib import Path

import pytest

from hdocsyngen.gold import gold
from hdocsyngen.table_export import export, header_rows, page_breaks
from hdocsyngen.templates import Builder, build
from hdocsyngen.templates import tables as T
from hdocsyngen.textpool import TextPool
from hdocsyngen.tree import Document, Furniture, Run, dumps, validate
from hdocsyngen.verify import verify_docx
from hdocsyngen.writers import docx

POOL = Path(__file__).parent / "data" / "invented_pool.jsonl"


@pytest.fixture(scope="module")
def pool():
    return TextPool.load(POOL)


def _covered_once(t):
    grid = [[0] * t["cols"] for _ in range(t["rows"])]
    for c in t["cells"]:
        for r in range(c["r"], c["r"] + c["rowspan"]):
            for k in range(c["c"], c["c"] + c["colspan"]):
                grid[r][k] += 1
    return all(v == 1 for row in grid for v in row)


@pytest.mark.parametrize("variant", T.VARIANTS)
def test_each_variant_is_valid_and_survives_docx(pool, variant):
    for seed in range(5):
        b = Builder(f"v-{variant}-{seed}", seed, pool)
        table = T.BUILDERS[variant](b)
        furniture = Furniture(header=[b.para([Run("כותרת")])], footer=[b.para([Run("1", "num", field="page")])])
        doc = Document(doc_id=b.doc_id, meta=b.meta("tables", "tables"), body=[table], furniture=furniture)
        assert validate(doc) == []
        assert verify_docx(doc, docx.write(doc)) == []
        (exported,) = export(gold(doc, dumps(doc)))
        assert _covered_once(exported)


def test_variant_shapes(pool):
    b = Builder("shapes", 3, pool)
    g = gold(Document("shapes", b.meta("tables", "tables"),
                      [T.grouped_header(b), T.matrix(b), T.long(b), T.sections(b)]), "")
    grouped, matrix, long_, sections = export(g)
    assert grouped["header_rows"] == 2
    assert any(c["colspan"] > 1 and c["r"] == 0 for c in grouped["cells"])
    # matrix: row k has k values, then its own label on the diagonal (column k + 1)
    cells = {(c["r"], c["c"]): c["text"] for c in matrix["cells"]}
    for k in range(1, matrix["rows"]):
        assert cells[(k, k + 1)] == cells[(k, 0)] if k + 1 < matrix["cols"] else True
    assert long_["rows"] >= 46
    assert sections["header_rows"] == 1
    section_rows = [r for r in range(1, sections["rows"])
                    if cells_in_row(sections, r)[0] and not any(cells_in_row(sections, r)[1:])]
    assert section_rows


def cells_in_row(t, r):
    row = sorted((c for c in t["cells"] if c["r"] == r), key=lambda c: c["c"])
    return [c["text"] for c in row]


def test_template_uses_two_to_four_variants_and_is_deterministic(pool):
    a, b = build("tables", "d", 11, pool), build("tables", "d", 11, pool)
    assert dumps(a) == dumps(b)
    tables = [x for x in a.body if x.type == "table"]
    assert 2 <= len(tables) <= 4


def test_header_rows_stops_at_first_body_row():
    t = {"rows": 3, "cols": 2, "cells": [
        {"r": 0, "c": 0, "rowspan": 2, "colspan": 1, "header": True},
        {"r": 0, "c": 1, "rowspan": 1, "colspan": 1, "header": True},
        {"r": 1, "c": 1, "rowspan": 1, "colspan": 1, "header": True},
        {"r": 2, "c": 0, "rowspan": 1, "colspan": 1, "header": False},
        {"r": 2, "c": 1, "rowspan": 1, "colspan": 1, "header": False}]}
    assert header_rows(t) == 2


def test_section_rows_follow_both_print_styles(pool):
    styles = set()
    for seed in range(20):
        b = Builder("s", seed, pool)
        (t,) = export(gold(Document("s", b.meta("tables", "tables"), [T.sections(b)]), ""))
        spans = [c for c in t["cells"] if c["r"] > 0 and c["c"] == 0 and c["colspan"] == t["cols"]]
        styles.add("span" if spans else "col0")
    assert styles == {"span", "col0"}


def test_page_breaks_from_producer_pages():
    table = {"cells": [{"r": r, "c": 0, "paragraphs": [f"p{r}"]} for r in range(5)]}
    producer = {"blocks": [{"id": "p0", "pages": [1]}, {"id": "p1", "pages": [1]}, {"id": "p2", "pages": [1, 2]},
                           {"id": "p3", "pages": [2]}, {"id": "p4", "pages": [3]}]}
    assert page_breaks(table, producer) == [3, 4]
    assert page_breaks(table, {"blocks": []}) is None
