"""`tables`: a table-heavy document for the tables and forms category (0032).

Each document holds 2-4 tables, each drawn from a seeded variant that exercises one or more failure classes of the
Phase 0 DEV taxonomy (heocr-agent-wiki records/tables/phase0-2026-11-25). Only the existing `hdoc_tree.v1` table
fields are used; variants that need schema additions (open sides, side-by-side blocks, rotation, forms) are proposed
in docs/tables_forms_design.md and wait on eval's review.

| Variant | Taxonomy |
|---|---|
| `grouped_header` | F3 two-level header (a group header spanning sub-columns) |
| `sections` | F4 in-table section rows (label in column 0, other cells empty), F2 two-line labels |
| `row_groups` | merged body cells: a row header spanning several rows |
| `long` | F11 page-spanning table, header repeated or not |
| `matrix` | F13 triangular matrix with diagonal labels |
| `wrapped` | F2 multi-line cells (several sentences per cell) |

Every variant draws `ruled` from all/header/rows/none (F6 borderless) and mixes decimals, percentages and amounts
(F8 number glyphs). Text comes from the pool (invented or CC0 text only, per AGENTS.md).
"""
from __future__ import annotations

from ..textpool import TextPool
from ..tree import Document, Furniture, Run, Table
from . import Builder, table_from_rows

VARIANTS = ("grouped_header", "sections", "row_groups", "long", "matrix", "wrapped")
RULED = ("all", "header", "rows", "none")


def _number(b: Builder) -> str:
    rng = b.rng
    kind = rng.choice(["dec2", "dec1", "int", "pct", "grouped"])
    if kind == "dec2":
        return f"{rng.uniform(0, 999):.2f}"
    if kind == "dec1":
        return f"{rng.uniform(0, 99):.1f}"
    if kind == "int":
        return str(rng.randint(0, 999))
    if kind == "pct":
        return f"{rng.uniform(0, 100):.1f}%"
    return f"{rng.randint(1_000, 9_999_999):,}"


def _label(b: Builder, lo: int = 1, hi: int = 4) -> str:
    return b.pool.phrase(b.rng, lo, hi)


def grouped_header(b: Builder) -> Table:
    rng = b.rng
    groups = rng.randint(1, 2)
    sub = [rng.randint(2, 3) for _ in range(groups)]
    cols = 1 + sum(sub)
    top = [_label(b, 1, 3)] + [""] * (cols - 1)
    second = [""] + [_label(b, 1, 2) for _ in range(cols - 1)]
    merges = {(0, 0): (2, 1)}
    c = 1
    for k in sub:
        top[c] = _label(b, 1, 3)
        merges[(0, c)] = (1, k)
        c += k
    rows = [top, second] + [[_label(b)] + [_number(b) for _ in range(cols - 1)] for _ in range(rng.randint(4, 12))]
    return table_from_rows(b, rows, header_rows=2, merges=merges, ruled=rng.choice(RULED))


def sections(b: Builder) -> Table:
    rng = b.rng
    cols = rng.randint(3, 5)
    rows = [[_label(b, 1, 3) for _ in range(cols)]]
    span_style = rng.random() < 0.5    # else the label sits in column 0, other cells empty
    merges: dict[tuple[int, int], tuple[int, int]] = {}
    for s in range(rng.randint(2, 4)):
        lead = f"({s + 1}) " if rng.random() < 0.5 else ""
        label = lead + _label(b, 2, 5) + (":" if rng.random() < 0.5 else "")
        if span_style:     # the label spans the table in print: one cell, colspan = cols (convention c)
            merges[(len(rows), 0)] = (1, cols)
        rows.append([label] + [""] * (cols - 1))
        for _ in range(rng.randint(2, 6)):
            name = _label(b, 1, 3) if rng.random() < 0.7 else _label(b, 6, 10)   # some labels wrap to two lines
            rows.append([name] + [_number(b) for _ in range(cols - 1)])
    return table_from_rows(b, rows, merges=merges, ruled=rng.choice(RULED))


def row_groups(b: Builder) -> Table:
    rng = b.rng
    cols = rng.randint(3, 5)
    rows = [[_label(b, 1, 2) for _ in range(cols)]]
    merges = {}
    for _ in range(rng.randint(2, 4)):
        k = rng.randint(2, 4)
        merges[(len(rows), 0)] = (k, 1)
        group = _label(b, 1, 3)
        for i in range(k):
            rows.append([group if i == 0 else ""] + [_label(b, 1, 2)] + [_number(b) for _ in range(cols - 2)])
    return table_from_rows(b, rows, merges=merges, ruled=rng.choice(["all", "rows"]))


def long(b: Builder) -> Table:
    rng = b.rng
    cols = rng.randint(2, 4)
    rows = [[_label(b, 1, 2) for _ in range(cols)]]
    for i in range(rng.randint(45, 90)):
        rows.append([str(i + 1) if rng.random() < 0.5 else _label(b, 1, 3)] + [_number(b) for _ in range(cols - 1)])
    return table_from_rows(b, rows, ruled=rng.choice(RULED), repeat_header=rng.random() < 0.6)


def matrix(b: Builder) -> Table:
    rng = b.rng
    n = rng.randint(5, 12)
    names = [_label(b, 1, 2) for _ in range(n)]
    cols = n + 1
    rows = [[""] + [names[0]] + [""] * (cols - 2)]
    for k in range(1, n):
        row = [names[k]] + [f"{rng.choice([5, 7.5, 9, 10, 13.5, 18, 20.5, 25.5]):.1f}" for _ in range(k)]
        row += [names[k]] + [""] * (cols - len(row) - 1)
        rows.append(row[:cols])
    return table_from_rows(b, rows, header_rows=0, ruled="none")


def wrapped(b: Builder) -> Table:
    rng = b.rng
    cols = rng.randint(3, 6)
    rows = [[_label(b, 1, 3) for _ in range(cols)]]
    for _ in range(rng.randint(2, 4)):
        row = [_label(b, 2, 4)]
        for _ in range(cols - 1):
            row.append(b.pool.sentence(rng, 8, 30) if rng.random() < 0.6 else _label(b, 1, 3))
        rows.append(row)
    return table_from_rows(b, rows, ruled=rng.choice(["all", "rows", "none"]))


BUILDERS = {"grouped_header": grouped_header, "sections": sections, "row_groups": row_groups, "long": long,
            "matrix": matrix, "wrapped": wrapped}


def build(doc_id: str, seed: int, pool: TextPool) -> Document:
    b = Builder(doc_id, seed, pool)
    rng = b.rng
    title = pool.phrase(rng, 3, 7)
    body = [b.para([Run(title)], align="center", style="title")]
    for name in rng.sample(VARIANTS, rng.randint(2, 4)):
        body.append(b.para([Run(pool.sentence(rng, 6, 20))], align="justify"))
        body.append(BUILDERS[name](b))
    furniture = Furniture(header=[b.para([Run(title)], align="end")],
                          footer=[b.para([Run("1", "num", field="page")], align="center")])
    return Document(doc_id=doc_id, meta=b.meta("tables", "tables"), body=body, notes=b.notes, furniture=furniture)
