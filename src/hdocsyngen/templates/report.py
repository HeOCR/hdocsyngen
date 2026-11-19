"""`report`: a report look. Numbered chapter headings, prose, bullet lists, a data table, footnotes and endnotes."""
from __future__ import annotations

from ..textpool import TextPool
from ..tree import AbstractNum, Document, Furniture, Level, Num, NumRef, Run
from .. import values as V
from . import Builder, bullet_numbering, table_from_rows


def heading_numbering() -> AbstractNum:
    return AbstractNum(3, [Level("decimal", "%1."), Level("decimal", "%1.%2."), Level("decimal", "%1.%2.%3.")])


def build(doc_id: str, seed: int, pool: TextPool) -> Document:
    b = Builder(doc_id, seed, pool)
    rng = b.rng
    title = pool.phrase(rng, 3, 7)
    body = [b.para([Run(title)], align="center", style="title"),
            b.para([Run("דוח מסכם, "), *V.date(rng)], align="center")]
    hn, bullets = Num(3, 3), Num(2, 2)
    prose = []
    for _ in range(rng.randint(3, 5)):
        body.append(b.heading(1, [Run(pool.phrase(rng, 2, 5))], num=NumRef(hn.id, 0)))
        for _ in range(rng.randint(1, 2)):
            p = b.para([r for _ in range(rng.randint(2, 4)) for r in (*b.prose_runs(0.3), Run(" "))][:-1],
                       align="justify")
            body.append(p)
            prose.append(p)
        for _ in range(rng.randint(1, 3)):
            body.append(b.heading(2, [Run(pool.phrase(rng, 2, 6))], num=NumRef(hn.id, 1)))
            for _ in range(rng.randint(1, 3)):
                p = b.para(b.prose_runs(0.35), align="justify")
                body.append(p)
                prose.append(p)
            if rng.random() < 0.35:
                for _ in range(rng.randint(2, 5)):
                    body.append(b.para([Run(pool.phrase(rng, 3, 10))], num=NumRef(bullets.id, 0)))
    # a data table after a random chapter
    cols = rng.randint(3, 5)
    header = [pool.phrase(rng, 1, 3) for _ in range(cols)]
    rows: list[list] = [header]
    for _ in range(rng.randint(4, 10)):
        row = [pool.phrase(rng, 1, 4)]
        for _ in range(cols - 1):
            row.append(rng.choice([f"{rng.randint(1, 99_999):,}", f"{round(rng.uniform(0, 100), 1)}%"]))
        rows.append(row)
    at = rng.randint(3, len(body))
    body.insert(at, table_from_rows(b, rows, ruled=rng.choice(["all", "header", "rows", "none"])))
    for p in rng.sample(prose, min(len(prose), rng.randint(1, 4))):
        b.footnote(p, "footnote")
    if rng.random() < 0.4:
        b.footnote(rng.choice([p for p in prose if not p.notes] or prose), "endnote")
    furniture = Furniture(header=[b.para([Run(title)], align="end")],
                          footer=[b.para([Run("1", "num", field="page")], align="center")])
    return Document(doc_id=doc_id, meta=b.meta("report", "report"), body=body, notes=b.notes, furniture=furniture,
                    abstract_nums=[bullet_numbering(), heading_numbering()], nums=[bullets, hn])
