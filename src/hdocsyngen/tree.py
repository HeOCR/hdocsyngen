"""The source tree (`hdoc_tree.v1`) and the gold it implies.

A document is a tree of blocks. The tree is the single source of truth: every writer (DOCX, HTML, ...) renders it, and
the gold is computed from it, never from a writer's output. Text is stored in logical order, NFC.

The gold format is owned by heocr-eval, who signed off v1 on 2026-11-19 (review of hdocsyngen#2). See docs/hdoc_tree_v1.md.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Literal, Union

SCHEMA = "hdoc_tree.v1"

Lang = Literal["he", "en", "num"]
# Value kinds carried by runs, so number measures can find them without a pattern.
VALUE_KINDS = ("amount", "date", "percent", "id", "item_no", "quantity", "email", "url", "ref")


@dataclass
class Run:
    text: str
    lang: Lang = "he"
    bold: bool = False
    italic: bool = False
    kind: str | None = None          # one of VALUE_KINDS, or None for prose
    field: str | None = None         # "page" | "numpages": the producer fills the text; `text` is a placeholder


@dataclass
class NumRef:
    num_id: int
    level: int                        # 0-based


@dataclass
class NoteAnchor:
    note_id: str
    offset: int                       # character offset in the paragraph's logical text, where the mark follows


@dataclass
class Paragraph:
    id: str
    runs: list[Run]
    type: Literal["paragraph"] = "paragraph"
    align: Literal["start", "justify", "center", "end"] = "start"
    num: NumRef | None = None
    notes: list[NoteAnchor] = field(default_factory=list)
    style: str | None = None          # "title", "list", "signature", ... (writer hint only)


@dataclass
class Heading:
    id: str
    level: int                        # 1-4
    runs: list[Run]
    type: Literal["heading"] = "heading"
    num: NumRef | None = None
    notes: list[NoteAnchor] = field(default_factory=list)


@dataclass
class Cell:
    r: int
    c: int
    paragraphs: list[Paragraph]
    rowspan: int = 1
    colspan: int = 1
    header: bool = False


@dataclass
class Table:
    id: str
    rows: int
    cols: int
    cells: list[Cell]
    type: Literal["table"] = "table"
    ruled: Literal["all", "header", "rows", "none", "inner"] = "all"   # inner: no outer border (open sides)
    repeat_header: bool = True
    col_widths: list[float] = field(default_factory=list)   # relative; empty = equal
    blocks: int = 1                   # > 1: printed as side-by-side blocks (layout.py); the tree stays logical


@dataclass
class PageBreak:
    id: str
    type: Literal["page_break"] = "page_break"


Block = Union[Paragraph, Heading, Table, PageBreak]


@dataclass
class Note:
    id: str
    kind: Literal["footnote", "endnote"]
    paragraphs: list[Paragraph]


@dataclass
class Level:
    fmt: str                          # decimal | hebrew1 | hebrew2 | lowerLetter | bullet
    text: str                         # Word pattern, e.g. "%1.%2." or "(%4)"
    start: int = 1
    restart: int | None = None        # lvlRestart (1-based level after which this level restarts); None = default


@dataclass
class AbstractNum:
    id: int
    levels: list[Level]


@dataclass
class Num:
    id: int
    abstract: int
    start_override: dict[int, int] = field(default_factory=dict)   # level -> start


@dataclass
class Furniture:
    header: list[Paragraph] = field(default_factory=list)
    footer: list[Paragraph] = field(default_factory=list)


@dataclass
class Meta:
    template: str
    look: str
    seed: int
    page: Literal["A4", "Letter"] = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    columns: int = 1
    font: str = "David Libre"
    font_size_pt: float = 12.0
    text_sources: list[dict] = field(default_factory=list)   # [{"id", "licence", "source"}]


@dataclass
class Document:
    doc_id: str
    meta: Meta
    body: list[Block]
    notes: list[Note] = field(default_factory=list)
    furniture: Furniture = field(default_factory=Furniture)
    abstract_nums: list[AbstractNum] = field(default_factory=list)
    nums: list[Num] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)   # hdoc_form.v1 structure over body blocks (templates/forms.py)
    schema: str = SCHEMA


# ---------------------------------------------------------------- serialisation

def to_dict(doc: Document) -> dict:
    return asdict(doc)


def dumps(doc: Document) -> str:
    return json.dumps(to_dict(doc), ensure_ascii=False, indent=1, sort_keys=False)


def _para(d: dict) -> Paragraph:
    return Paragraph(id=d["id"], runs=[Run(**r) for r in d["runs"]], align=d.get("align", "start"),
                     num=NumRef(**d["num"]) if d.get("num") else None,
                     notes=[NoteAnchor(**n) for n in d.get("notes", [])], style=d.get("style"))


def _block(d: dict) -> Block:
    t = d["type"]
    if t == "paragraph":
        return _para(d)
    if t == "heading":
        return Heading(id=d["id"], level=d["level"], runs=[Run(**r) for r in d["runs"]],
                       num=NumRef(**d["num"]) if d.get("num") else None,
                       notes=[NoteAnchor(**n) for n in d.get("notes", [])])
    if t == "table":
        return Table(id=d["id"], rows=d["rows"], cols=d["cols"], ruled=d.get("ruled", "all"),
                     repeat_header=d.get("repeat_header", True), col_widths=d.get("col_widths", []),
                     blocks=d.get("blocks", 1),
                     cells=[Cell(r=c["r"], c=c["c"], rowspan=c.get("rowspan", 1), colspan=c.get("colspan", 1),
                                 header=c.get("header", False), paragraphs=[_para(p) for p in c["paragraphs"]])
                            for c in d["cells"]])
    if t == "page_break":
        return PageBreak(id=d["id"])
    raise ValueError(f"unknown block type {t!r}")


def from_dict(d: dict) -> Document:
    # "-draft" trees (written before eval's sign-off) have the same structure and load as v1.
    if d.get("schema") not in (SCHEMA, SCHEMA + "-draft"):
        raise ValueError(f"schema {d.get('schema')!r}, expected {SCHEMA!r}")
    return Document(
        doc_id=d["doc_id"], meta=Meta(**d["meta"]), body=[_block(b) for b in d["body"]],
        notes=[Note(id=n["id"], kind=n["kind"], paragraphs=[_para(p) for p in n["paragraphs"]]) for n in d["notes"]],
        furniture=Furniture(header=[_para(p) for p in d["furniture"]["header"]],
                            footer=[_para(p) for p in d["furniture"]["footer"]]),
        abstract_nums=[AbstractNum(id=a["id"], levels=[Level(**lv) for lv in a["levels"]]) for a in d["abstract_nums"]],
        nums=[Num(id=n["id"], abstract=n["abstract"], start_override={int(k): v for k, v in n["start_override"].items()})
              for n in d["nums"]],
        forms=d.get("forms", []))


def loads(s: str) -> Document:
    return from_dict(json.loads(s))


# ---------------------------------------------------------------- text and validation

def text_of(p: Paragraph | Heading) -> str:
    """The logical text of a paragraph. Field runs (page numbers) are left out: the producer fills them."""
    return "".join(r.text for r in p.runs if r.field is None)


def iter_paragraphs(doc: Document):
    """Every paragraph-like block in document order, with its container: ("body"|table id|note id|"header"|"footer")."""
    for b in doc.body:
        if isinstance(b, (Paragraph, Heading)):
            yield "body", b
        elif isinstance(b, Table):
            for cell in sorted(b.cells, key=lambda c: (c.r, c.c)):
                for p in cell.paragraphs:
                    yield b.id, p
    for n in doc.notes:
        for p in n.paragraphs:
            yield n.id, p
    for p in doc.furniture.header:
        yield "header", p
    for p in doc.furniture.footer:
        yield "footer", p


def validate(doc: Document) -> list[str]:
    """Structural problems; an empty list means the tree is well formed."""
    problems: list[str] = []
    ids: set[str] = set()

    def need_unique(i: str):
        if i in ids:
            problems.append(f"duplicate id {i}")
        ids.add(i)

    for b in doc.body:
        need_unique(b.id)
    for container, p in iter_paragraphs(doc):
        if container != "body":
            need_unique(p.id)
        for r in p.runs:
            if r.text != unicodedata.normalize("NFC", r.text):
                problems.append(f"{p.id}: run not NFC")
            if r.kind is not None and r.kind not in VALUE_KINDS:
                problems.append(f"{p.id}: unknown run kind {r.kind}")
        if isinstance(p, Heading) and not 1 <= p.level <= 4:
            problems.append(f"{p.id}: heading level {p.level}")
    note_ids = {n.id for n in doc.notes}
    anchored: list[str] = []
    for _, p in iter_paragraphs(doc):
        for a in p.notes:
            anchored.append(a.note_id)
            if a.note_id not in note_ids:
                problems.append(f"{p.id}: anchor to missing note {a.note_id}")
            if not 0 <= a.offset <= len(text_of(p)):
                problems.append(f"{p.id}: anchor offset {a.offset} outside text")
    for n in doc.notes:
        need_unique(n.id)
        if anchored.count(n.id) != 1:
            problems.append(f"note {n.id} anchored {anchored.count(n.id)} times")
    abstract = {a.id: a for a in doc.abstract_nums}
    nums = {n.id: n for n in doc.nums}
    for n in doc.nums:
        if n.abstract not in abstract:
            problems.append(f"num {n.id}: missing abstract {n.abstract}")
    for _, p in iter_paragraphs(doc):
        if p.num is not None:
            if p.num.num_id not in nums:
                problems.append(f"{p.id}: missing num {p.num.num_id}")
            elif not 0 <= p.num.level < len(abstract[nums[p.num.num_id].abstract].levels):
                problems.append(f"{p.id}: level {p.num.level} not defined")
    for b in doc.body:
        if isinstance(b, Table):
            grid = [[None] * b.cols for _ in range(b.rows)]
            for cell in b.cells:
                for rr in range(cell.r, cell.r + cell.rowspan):
                    for cc in range(cell.c, cell.c + cell.colspan):
                        if not (0 <= rr < b.rows and 0 <= cc < b.cols):
                            problems.append(f"{b.id}: cell ({cell.r},{cell.c}) spans outside the grid")
                        elif grid[rr][cc] is not None:
                            problems.append(f"{b.id}: grid slot ({rr},{cc}) covered twice")
                        else:
                            grid[rr][cc] = (cell.r, cell.c)
            if any(slot is None for row in grid for slot in row):
                problems.append(f"{b.id}: grid has empty slots")
            if b.col_widths and len(b.col_widths) != b.cols:
                problems.append(f"{b.id}: {len(b.col_widths)} widths for {b.cols} columns")
            if b.ruled not in ("all", "header", "rows", "none", "inner"):
                problems.append(f"{b.id}: unknown ruled {b.ruled!r}")
            if b.blocks < 1:
                problems.append(f"{b.id}: blocks must be >= 1")
            elif b.blocks > 1:
                heads = {c.r for c in b.cells if c.header}
                n_head = next((r for r in range(b.rows) if r not in heads), b.rows)
                if heads != set(range(n_head)) or any(c.header and c.r + c.rowspan > n_head for c in b.cells):
                    problems.append(f"{b.id}: side-by-side blocks need leading header rows only")
                if any(c.rowspan > 1 for c in b.cells if c.r >= n_head):
                    problems.append(f"{b.id}: side-by-side blocks cannot have body row spans")
                if b.rows - n_head < b.blocks:
                    problems.append(f"{b.id}: fewer body rows than blocks")
    problems += _validate_forms(doc)
    return problems


FIELD_KINDS = ("text", "number", "date", "checkbox", "choice", "signature")
FIELD_SLOTS = ("line", "box", "cell")


def form_fields(children: list[dict]):
    """Every field under a section's children, groups and nested sections included, in order."""
    for ch in children:
        if ch["type"] == "field":
            yield ch
        elif ch["type"] == "group":
            for column in ch["columns"]:
                yield from form_fields(column)
        elif ch["type"] == "section":
            yield from form_fields(ch["children"])


def _validate_forms(doc: Document) -> list[str]:
    problems: list[str] = []
    paras = {p.id for _, p in iter_paragraphs(doc)}
    tables = {b.id for b in doc.body if isinstance(b, Table)}
    for form in doc.forms:
        seen: set[str] = set()
        for section in form["sections"]:
            for ch in section["children"]:
                if ch["type"] == "table" and ch["table"] not in tables:
                    problems.append(f"{form['id']}: missing table {ch['table']}")
            for f in form_fields(section["children"]):
                if f["id"] in seen:
                    problems.append(f"{form['id']}: duplicate field {f['id']}")
                seen.add(f["id"])
                if f["kind"] not in FIELD_KINDS or f["slot"] not in FIELD_SLOTS:
                    problems.append(f"{f['id']}: kind {f['kind']!r} / slot {f['slot']!r}")
                if not isinstance(f["value"], str):
                    problems.append(f"{f['id']}: value must be a string")
                if f["kind"] == "checkbox" and f["value"] not in ("checked", "unchecked"):
                    problems.append(f"{f['id']}: checkbox value {f['value']!r}")
                missing = [p for p in f["paragraphs"] if p not in paras]
                if missing or not f["paragraphs"]:
                    problems.append(f"{f['id']}: printed by missing paragraphs {missing}")
    return problems


# ---------------------------------------------------------------- colour twin (design note §3.3, check 1)

def twin_colours(doc: Document) -> dict[str, tuple[int, int, int]]:
    """A unique near-black colour per paragraph-like block (body, cells, notes, furniture), by document order.

    Index k is coded as (r, g, b) with each channel in 0..31 (15 bits, 32,767 blocks); index 0 is never used, so plain
    black (0, 0, 0) means "not ours". The colours are invisible to a reader and do not change layout.
    """
    out = {}
    for k, (_, p) in enumerate(iter_paragraphs(doc), start=1):
        if k >= 1 << 15:
            raise ValueError("too many blocks for the colour twin")
        out[p.id] = ((k >> 10) & 31, (k >> 5) & 31, k & 31)
    return out


def colour_index(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return (r << 10) | (g << 5) | b if max(rgb) <= 31 else -1
