"""Dense staircase matrices (template ``tables_dense``)."""
from pathlib import Path

from hdocsyngen.gold import gold
from hdocsyngen.table_export import export
from hdocsyngen.templates import TEMPLATES, Builder, build
from hdocsyngen.templates import tables_dense as D
from hdocsyngen.textpool import TextPool
from hdocsyngen.tree import Document, Furniture, Run, dumps, validate
from hdocsyngen.verify import verify_docx
from hdocsyngen.writers import docx

POOL = Path(__file__).parent / "data" / "invented_pool.jsonl"


def _grid(t):
    g = [[""] * t["cols"] for _ in range(t["rows"])]
    for c in t["cells"]:
        g[c["r"]][c["c"]] = c["text"]
    return g


def test_staircases_are_long_and_hold_their_diagonal_labels():
    pool = TextPool.load(POOL)
    seen_top, seen_header = set(), set()
    for seed in range(12):
        b = Builder(f"dense-{seed}", seed, pool)
        table = D.staircase(b)
        doc = build("tables_dense", f"dense-doc-{seed}", seed, pool)
        assert validate(doc) == []
        assert verify_docx(doc, docx.write(doc)) == []
        one = Document(doc_id=b.doc_id, meta=b.meta("tables_dense", "tables"), body=[table],
                       furniture=Furniture(header=[b.para([Run("כותרת")])], footer=[b.para([Run("1", "num", field="page")])]))
        (t,) = export(gold(one, dumps(one)))
        g = _grid(t)
        h = t["header_rows"]
        seen_header.add(h)
        n = t["cols"]
        assert D.ROWS[0] <= n <= D.ROWS[1] and t["rows"] == h + n
        first = g[h]
        seen_top.add("diag_only" if first[0] == "" else "label_row")
        assert first[1] and all(v == "" for v in first[2:])
        for k in range(1, n):
            row = g[h + k]
            values = row[1:k + 1]
            assert all(v and any(ch.isdigit() for ch in v) for v in values)
            if k < n - 1:
                assert row[k + 1] == row[0]                     # the name again, as the diagonal label
                assert all(v == "" for v in row[k + 2:])
    assert seen_top == {"diag_only", "label_row"} and seen_header == {0, 1}


def test_the_template_is_registered_and_deterministic():
    pool = TextPool.load(POOL)
    assert "tables_dense" in TEMPLATES
    assert dumps(build("tables_dense", "x", 5, pool)) == dumps(build("tables_dense", "x", 5, pool))
