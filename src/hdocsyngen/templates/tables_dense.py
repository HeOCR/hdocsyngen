"""Dense staircase matrices: the F13 matrix at 15+ rows (template ``tables_dense``).

The `matrix` variant in ``tables`` stays small (5–12 names). Real triangular fare or distance matrices run longer,
and there a detector's row bands drift: two printed rows fall in one band, or a band comes out empty. This template
makes born-digital pages of such matrices only, so a fix for them can be selected on TRAIN.

Each matrix has n names (15–22). Row k holds its name, k values, then the name again as the diagonal label in its
own cell. Variants, drawn per matrix:
- ``top``: either the first name has its own row with a label (``label_row``), or only the diagonal label above the
  first column of values (``diag_only``);
- a one-line header above the name column (half the matrices; then it is header row 0);
- values: whole numbers (2–120) or half steps (5.0–40.5);
- rulings: none, or rows.
"""
from __future__ import annotations

from ..textpool import TextPool
from ..tree import Document, Furniture, Run, Table
from . import Builder, table_from_rows
from .tables import _label

ROWS = (15, 22)


def staircase(b: Builder) -> Table:
    rng = b.rng
    n = rng.randint(*ROWS)
    names = [_label(b, 1, 2) for _ in range(n)]
    halves = rng.random() < 0.5

    def value() -> str:
        return f"{rng.randint(10, 81) / 2:.1f}" if halves else str(rng.randint(2, 120))

    cols = n
    rows = []
    if rng.random() < 0.5:  # a header over the name column
        rows.append([_label(b, 1, 2)] + [""] * (cols - 1))
    header_rows = len(rows)
    if rng.random() < 0.5:  # diag_only: the first name only as the label over the first values column
        rows.append([""] + [names[0]] + [""] * (cols - 2))
    else:                    # label_row: the first name has a row of its own
        rows.append([names[0]] + [names[0]] + [""] * (cols - 2))
    for k in range(1, n):
        row = [names[k]] + [value() for _ in range(k)]
        if k < n - 1:
            row.append(names[k])
        rows.append(row + [""] * (cols - len(row)))
    return table_from_rows(b, rows, header_rows=header_rows, ruled=rng.choice(["none", "none", "rows"]))


def build(doc_id: str, seed: int, pool: TextPool) -> Document:
    b = Builder(doc_id, seed, pool)
    rng = b.rng
    title = pool.phrase(rng, 3, 7)
    body = [b.para([Run(title)], align="center", style="title")]
    for _ in range(rng.randint(1, 2)):
        body.append(b.para([Run(pool.sentence(rng, 6, 20))], align="justify"))
        body.append(staircase(b))
    furniture = Furniture(header=[b.para([Run(title)], align="end")],
                          footer=[b.para([Run("1", "num", field="page")], align="center")])
    return Document(doc_id=doc_id, meta=b.meta("tables_dense", "tables"), body=body, notes=b.notes,
                    furniture=furniture)
