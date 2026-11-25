"""`forms`: a filled-in form for the tables and forms category (0032), with its `hdoc_form.v1` structure.

A form is drawn as ordinary tree blocks, so every writer renders it unchanged: section titles are headings, and fields
are paragraphs or table cells. The form's structure is recorded next to the body in `Document.forms`, and each field
names the paragraphs that print it. The gold structure is then exact, and a producer layer gives each field's pages.

| Layout | Slot | What is printed |
|---|---|---|
| `lines` | line | one field per paragraph: "label: value", or "label: ________" when it is not filled in |
| `boxes` | box | a ruled 2-column table, label beside value; with `group`, two pairs side by side (4 columns) |
| `cells` | cell | a ruled table with the labels in the top row and the values under them |
| `checks` | box | checkboxes, one per paragraph: "[X] label" or "[ ] label" (kind `checkbox`) |
| `choice` | line | "label: [ ] option [X] option [ ] option", value = the marked option's text (kind `choice`) |

**Check marks** are text every open Hebrew family draws: "[X]"/"[ ]" or "(X)"/"( )", one style per document. None
of our 17 installed Hebrew families has ☐/☒ (U+2610/2612), and `fit_font` needs one family for every character;
box glyphs wait on a per-run symbol font in the tree.
| `items` | - | a table inside the form (rows of items with quantities and amounts), as in the `tables` template |
| `declaration` | line | prose from the pool, then signature and date lines (kind `signature`, value `""`) |

**Values are provided, never written by hand.** They come from `values.py` (amounts, dates, IDs failing the check
digit, example.com addresses) and from the fixed lists below. Those lists hold only placeholders: the standard sample
names of Israeli forms ("ישראל ישראלי"), "לדוגמה" street and place names, and reference numbers. No phone numbers.
About a fifth of the fields are left unfilled (value `""`). Labels, titles and options are our own text (CC0).
"""
from __future__ import annotations

from ..textpool import TextPool
from ..tree import Document, Furniture, Paragraph, Run, Table
from .. import values as V
from . import Builder, table_from_rows

LAYOUTS = ("lines", "boxes", "cells", "checks", "choice", "items", "declaration")
BLANK = "________"
MARKS = (("[X]", "[ ]"), ("(X)", "( )"))

TITLES = ["טופס בקשה", "טופס הרשמה", "טופס עדכון פרטים", "טופס הצהרה", "בקשה להחזר תשלום", "טופס פנייה",
          "בקשה לקבלת אישור", "טופס דיווח שנתי"]
SECTIONS = ["פרטי המבקש", "פרטי הפנייה", "פרטי הנכס", "פרטי התשלום", "פרטי התאגיד", "פרטים נוספים", "פרטי הבקשה",
            "פרטי איש הקשר"]
SAMPLE_NAMES = ["ישראל ישראלי", "ישראלה ישראלית", "פלוני אלמוני", "פלונית אלמונית"]
SAMPLE_PLACES = ["יישוב לדוגמה", "עיר לדוגמה", "מושב לדוגמה"]
SAMPLE_ORGS = ['חברה לדוגמה בע"מ', "עמותה לדוגמה", "שותפות לדוגמה"]
CHECK_LABELS = ["אני מאשר/ת את נכונות הפרטים", "מצורפים מסמכים", "הבקשה דחופה", "יש לשלוח עדכונים בדואר אלקטרוני",
                "הנכס בבעלות המבקש", "קיים חוב פתוח", "נדרש תרגום"]
CHOICES = [("סוג הבקשה", ["חדשה", "חידוש", "עדכון"]), ("אופן המשלוח", ["דואר", "דואר אלקטרוני", "איסוף עצמי"]),
           ("מצב משפחתי", ["רווק/ה", "נשוי/אה", "אחר"]), ("סוג הנכס", ["דירה", "בית", "מגרש", "אחר"])]


def _street(rng) -> list[Run]:
    return [Run("רחוב הדוגמה "), Run(str(rng.randint(1, 120)), "num")]


# label -> (kind, value runs); every value is fictional (module docstring)
FIELDS = {
    "שם מלא": ("text", lambda rng: [Run(rng.choice(SAMPLE_NAMES))]),
    "שם התאגיד": ("text", lambda rng: [Run(rng.choice(SAMPLE_ORGS))]),
    "מספר זהות": ("number", lambda rng: V.fake_id(rng)),
    "מספר תאגיד": ("number", lambda rng: V.fake_id(rng, company=True)),
    "כתובת": ("text", _street),
    "יישוב": ("text", lambda rng: [Run(rng.choice(SAMPLE_PLACES))]),
    "מיקוד": ("number", lambda rng: [Run(f"{rng.randint(1000000, 9999999)}", "num")]),
    "דואר אלקטרוני": ("text", lambda rng: V.email(rng)),
    "תאריך לידה": ("date", lambda rng: V.date(rng, 1940, 2005)),
    "תאריך הגשה": ("date", lambda rng: V.date(rng)),
    "מספר תיק": ("number", lambda rng: V.tender_ref(rng)),
    "סכום מבוקש": ("number", lambda rng: V.amount(rng, 100, 50_000)),
    "מספר חשבון": ("number", lambda rng: [Run(f"{rng.randint(10000, 999999)}", "num")]),
    "שטח במ\"ר": ("number", lambda rng: [Run(str(rng.randint(20, 900)), "num", kind="quantity")]),
    "מספר נפשות": ("number", lambda rng: [Run(str(rng.randint(1, 9)), "num", kind="quantity")]),
    "הערות": ("text", None),     # free text from the pool
}


def _value(b: Builder, label: str) -> list[Run]:
    kind, fn = FIELDS[label]
    if fn is None:
        return [Run(b.pool.phrase(b.rng, 2, 8))]
    return fn(b.rng)


def _text(runs: list[Run]) -> str:
    return "".join(r.text for r in runs)


class Form:
    """Collects one form's structure while its blocks are drawn."""

    def __init__(self, b: Builder, title: str):
        self.b, self.n = b, 0
        self.record = {"id": b.id("f"), "title": title, "sections": []}
        self.checked, self.unchecked = b.rng.choice(MARKS)
        self.used: set[str] = set()      # labels are drawn without replacement within a form

    def draw(self, labels: list, k: int) -> list:
        free = [x for x in labels if (x[0] if isinstance(x, tuple) else x) not in self.used]
        picked = self.b.rng.sample(free, min(k, len(free)))
        self.used |= {x[0] if isinstance(x, tuple) else x for x in picked}
        return picked

    def field(self, label: str, kind: str, slot: str, value: str, paragraphs: list[str]) -> dict:
        self.n += 1
        return {"type": "field", "id": f"{self.record['id']}.{self.n}", "label": label, "value": value, "kind": kind,
                "slot": slot, "paragraphs": paragraphs}

    def filled(self) -> bool:
        return self.b.rng.random() >= 0.2


def _labels(f: Form, k: int) -> list[str]:
    picked = f.draw([label for label in FIELDS if label != "הערות"], k)
    return picked + (f.draw(["הערות"], 1) if f.b.rng.random() < 0.3 else [])


def lines(f: Form) -> tuple[list, list]:
    b, blocks, children = f.b, [], []
    labels = _labels(f, b.rng.randint(2, 5))
    if not labels:
        return checks(f)      # this form's field labels are used up
    for label in labels:
        sep = b.rng.choice([": ", ":  ", " - "])
        value = _value(b, label) if f.filled() else []
        p = b.para([Run(label + sep), *(value or [Run(BLANK)])])
        blocks.append(p)
        children.append(f.field(label, FIELDS[label][0], "line", _text(value), [p.id]))
    return blocks, children


def _pair_rows(f: Form, labels: list[str]) -> tuple[list[list], list[tuple[str, str, str]]]:
    rows, fields = [], []
    for label in labels:
        value = _value(f.b, label) if f.filled() else []
        rows.append([label, value])
        fields.append((label, FIELDS[label][0], _text(value)))
    return rows, fields


def boxes(f: Form) -> tuple[list, list]:
    b = f.b
    labels = _labels(f, b.rng.randint(2, 6))
    if not labels:
        return checks(f)
    rows, fields = _pair_rows(f, labels)
    grouped = len(rows) >= 4 and b.rng.random() < 0.5
    if grouped:          # two label/value pairs per row: a group of two columns
        half = (len(rows) + 1) // 2
        left, right = rows[:half], rows[half:] + [["", []]] * (2 * half - len(rows))
        grid = [[lab, val, lab2, val2] for (lab, val), (lab2, val2) in zip(left, right)]
    else:
        grid = rows
    t = table_from_rows(b, grid, header_rows=0, ruled=b.rng.choice(["all", "rows", "inner"]))
    by_pos = {(c.r, c.c): c for c in t.cells}
    out = []
    for i, (label, kind, value) in enumerate(fields):
        if grouped:
            half = (len(rows) + 1) // 2
            r, c = (i, 1) if i < half else (i - half, 3)
        else:
            r, c = i, 1
        out.append(f.field(label, kind, "box", value, [by_pos[(r, c - 1)].paragraphs[0].id,
                                                       by_pos[(r, c)].paragraphs[0].id]))
    if grouped:
        half = (len(rows) + 1) // 2
        # column 0 is the right one (read first in RTL); each column top to bottom
        children = [{"type": "group", "columns": 2, "children": out, "table": t.id}]
    else:
        children = [*out]
    return [t], children


def cells(f: Form) -> tuple[list, list]:
    b = f.b
    labels = _labels(f, b.rng.randint(2, 5))
    if not labels:
        return checks(f)
    rows, fields = _pair_rows(f, labels)
    t = table_from_rows(b, [[lab for lab, _ in rows], [val for _, val in rows]], header_rows=1, ruled="all")
    by_pos = {(c.r, c.c): c for c in t.cells}
    return [t], [f.field(label, kind, "cell", value, [by_pos[(0, i)].paragraphs[0].id, by_pos[(1, i)].paragraphs[0].id])
                 for i, (label, kind, value) in enumerate(fields)]


def checks(f: Form) -> tuple[list, list]:
    b, blocks, children = f.b, [], []
    labels = f.draw(CHECK_LABELS, b.rng.randint(2, 4))
    if not labels:
        return choice(f)
    for label in labels:
        on = b.rng.random() < 0.5
        p = b.para([Run(f"{f.checked if on else f.unchecked} {label}")])
        blocks.append(p)
        children.append(f.field(label, "checkbox", "box", "checked" if on else "unchecked", [p.id]))
    return blocks, children


def choice(f: Form) -> tuple[list, list]:
    b = f.b
    label, options = (f.draw(CHOICES, 1) or [b.rng.choice(CHOICES)])[0]
    marked = b.rng.choice(options) if f.filled() else None
    marks = "  ".join(f"{f.checked if o == marked else f.unchecked} {o}" for o in options)
    p = b.para([Run(f"{label}: {marks}")])
    return [p], [f.field(label, "choice", "line", marked or "", [p.id])]


def items(f: Form) -> tuple[list, list]:
    b = f.b
    header = ["מס'", "תיאור", "כמות", "סכום"]
    rows = [header] + [[str(i + 1), b.pool.phrase(b.rng, 1, 4), str(b.rng.randint(1, 40)),
                        f"{b.rng.randint(10, 99_999):,}"] for i in range(b.rng.randint(2, 6))]
    t = table_from_rows(b, rows, ruled=b.rng.choice(["all", "rows"]))
    return [t], [{"type": "table", "table": t.id}]


def declaration(f: Form) -> tuple[list, list]:
    b = f.b
    blocks = [b.para([Run(b.pool.sentence(b.rng, 10, 30))], align="justify")]
    date = V.date(b.rng) if f.filled() else []
    sig = b.para([Run("חתימה: " + BLANK)])
    when = b.para([Run("תאריך: "), *(date or [Run(BLANK)])])
    blocks += [sig, when]
    return blocks, [f.field("חתימה", "signature", "line", "", [sig.id]),
                    f.field("תאריך", "date", "line", _text(date), [when.id])]


BUILDERS = {"lines": lines, "boxes": boxes, "cells": cells, "checks": checks, "choice": choice, "items": items,
            "declaration": declaration}


def build(doc_id: str, seed: int, pool: TextPool) -> Document:
    b = Builder(doc_id, seed, pool)
    rng = b.rng
    title = rng.choice(TITLES)
    form = Form(b, title)
    body: list = [b.para([Run(title)], align="center", style="title")]
    numbered = rng.random() < 0.5
    for i, name in enumerate(rng.sample(SECTIONS, rng.randint(2, 4))):
        shown = f"{i + 1}. {name}" if numbered else name
        head = b.heading(2, [Run(shown)])
        body.append(head)
        section = {"title": shown, "heading": head.id, "children": []}
        parts = [rng.choice(("lines", "boxes", "cells", "checks", "choice"))]
        if rng.random() < 0.35:
            parts.append(rng.choice(("items", "choice", "checks")))
        for layout in parts:
            blocks, children = BUILDERS[layout](form)
            body += blocks
            section["children"] += children
        form.record["sections"].append(section)
    blocks, children = declaration(form)
    body += blocks
    form.record["sections"].append({"title": None, "heading": None, "children": children})
    furniture = Furniture(header=[b.para([Run(title)], align="end")],
                          footer=[b.para([Run("1", "num", field="page")], align="center")])
    return Document(doc_id=doc_id, meta=b.meta("forms", "forms"), body=body, notes=b.notes, furniture=furniture,
                    forms=[form.record])
