"""`tender`: a tender or call-for-bids look. Invented structure; prose from the pool; values generated."""
from __future__ import annotations
from collections.abc import Callable

from ..textpool import TextPool
from ..tree import Document, Furniture, Num, NumRef, Run
from .. import values as V
from . import Builder, bullet_numbering, section_numbering, table_from_rows

SECTION_TITLES = ["הגדרות", "כללי", "תנאי סף", "היקף העבודה", "לוח זמנים", "ערבויות", "ביטוח", "תנאי תשלום",
                  "אופן הגשת ההצעה", "בחינת ההצעות", "התחייבויות הספק", "סודיות", "הוראות שונות"]
UNITS = ["יח'", "מ\"ר", "מ\"א", "ק\"ג", "שעה", "חודש", "קומפלט", "טון"]


def build(doc_id: str, seed: int, pool: TextPool, *, reject_cell: Callable[[str], bool] | None = None) -> Document:
    b = Builder(doc_id, seed, pool)
    rng = b.rng
    ref = V.tender_ref(rng)
    body = []

    body.append(b.para([Run("מכרז פומבי מס' "), *ref], align="center", style="title"))
    body.append(b.para([Run(pool.phrase(rng, 3, 7))], align="center", style="title"))
    body.append(b.para([Run("תאריך: "), *V.date(rng)], align="end"))
    body.append(b.para([Run("לכבוד")]))
    body.append(b.para([Run("המציעים")]))
    body.append(b.para([Run("הנדון: "), Run(pool.phrase(rng, 3, 8))], style="subject"))
    body.append(b.para(b.prose_runs(0.5), align="justify"))

    sec = Num(1, 1)
    bullets = Num(2, 2)
    titles = rng.sample(SECTION_TITLES, rng.randint(4, 7))
    numbered = []
    for t in titles:
        body.append(b.heading(1, [Run(t)], num=NumRef(sec.id, 0)))
        for _ in range(rng.randint(2, 5)):
            p = b.para(b.prose_runs(), align="justify", num=NumRef(sec.id, 1))
            body.append(p)
            numbered.append(p)
            for _ in range(rng.choice([0, 0, 1, 2, 3])):
                q = b.para(b.prose_runs(0.4, 4, 25), align="justify", num=NumRef(sec.id, 2))
                body.append(q)
                numbered.append(q)
                if rng.random() < 0.25:
                    for _ in range(rng.randint(2, 4)):
                        body.append(b.para(b.prose_runs(0.2, 3, 15), num=NumRef(sec.id, 3)))
        if rng.random() < 0.3:
            for _ in range(rng.randint(2, 4)):
                body.append(b.para([Run(pool.phrase(rng, 3, 9))], num=NumRef(bullets.id, 0)))

    for p in rng.sample(numbered, min(len(numbered), rng.randint(1, 3))):
        b.footnote(p)

    # bill of quantities
    body.append(b.heading(1, [Run('כתב כמויות')], num=NumRef(sec.id, 0)))
    header = ["מס' סעיף", "תיאור", "יחידה", "כמות", "מחיר יחידה", 'סה"כ']
    rows: list[list] = [header]
    merges = {}
    total = 0
    n_items = rng.randint(6, 14)
    group_at = rng.randint(1, n_items - 2) if rng.random() < 0.5 else None
    for i in range(n_items):
        if group_at is not None and i == group_at:
            merges[(len(rows), 0)] = (1, 6)
            rows.append([pool.phrase(rng, 2, 5)] + [""] * 5)
        # Draw the linked figures together so quantity, price, subtotal and total still reconcile.
        for _ in range(1000):
            qty = rng.randint(1, 500)
            price = rng.randint(10, 20_000)
            item = V.item_no(rng)
            figures = [f"{qty:,}", f"{price:,}", f"{qty * price:,}"]
            if reject_cell is None or not any(reject_cell(v) for v in (item, *figures)):
                break
        else:
            raise ValueError("No eligible tender table figures for this seed")
        total += qty * price
        rows.append([item, pool.phrase(rng, 2, 7), rng.choice(UNITS), *figures])
    merges[(len(rows), 0)] = (1, 5)
    rows.append(['סה"כ'] + [""] * 4 + [f"{total:,}"])
    body.append(table_from_rows(b, rows, merges=merges, ruled=rng.choice(["all", "all", "header", "rows"]),
                                col_widths=[0.11, 0.37, 0.1, 0.1, 0.15, 0.17]))
    body.append(b.para(b.prose_runs(0.3, 5, 25), align="justify"))

    body.append(b.para([Run("חתימת המציע: ____________")], style="signature"))
    body.append(b.para([Run("תאריך: ____________")], style="signature"))

    furniture = Furniture(
        header=[b.para([Run("מכרז מס' "), *[Run(r.text, r.lang, kind=r.kind) for r in ref]], align="center")],
        footer=[b.para([Run("עמוד "), Run("1", "num", field="page"), Run(" מתוך "),
                        Run("1", "num", field="numpages")], align="center")])
    return Document(doc_id=doc_id, meta=b.meta("tender", "tender"), body=body, notes=b.notes, furniture=furniture,
                    abstract_nums=[section_numbering(), bullet_numbering()], nums=[sec, bullets])
