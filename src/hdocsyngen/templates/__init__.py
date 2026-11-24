"""Document templates by look (design note §4.1). Each template builds a source tree from a seed and a text pool."""
from __future__ import annotations

import random

from ..textpool import TextPool
from ..tree import (AbstractNum, Cell, Document, Furniture, Heading, Level, Meta, Note, NoteAnchor, Num, NumRef,
                    Paragraph, Run, Table, text_of)
from .. import values as V

OPEN_FONTS = ["David Libre", "Frank Ruhl Libre", "Miriam Libre", "Noto Sans Hebrew", "Noto Serif Hebrew", "Alef",
              "Heebo", "Rubik", "Assistant", "Arimo", "Tinos"]


class Builder:
    """Allocates ids and holds the parts of one document while a template fills it."""

    def __init__(self, doc_id: str, seed: int, pool: TextPool):
        self.doc_id, self.seed, self.pool = doc_id, seed, pool
        pool.used = {}                     # sources are recorded per document
        self.rng = random.Random(seed)
        self._n = 0
        self.notes: list[Note] = []

    def id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n:04d}"

    def para(self, runs: list[Run], **kw) -> Paragraph:
        return Paragraph(id=self.id("p"), runs=runs, **kw)

    def heading(self, level: int, runs: list[Run], num: NumRef | None = None) -> Heading:
        return Heading(id=self.id("h"), level=level, runs=runs, num=num)

    def with_value(self, sentence: str, value: list[Run]) -> list[Run]:
        """The sentence with a value inserted between two words (logical order), as one run sequence."""
        words = sentence.split()
        k = self.rng.randint(1, max(1, len(words) - 1))
        return [Run(" ".join(words[:k]) + " "), *value, Run(" " + " ".join(words[k:]))]

    def value(self) -> list[Run]:
        f = self.rng.choices([V.amount, V.date, V.percent, V.fake_id, V.email, V.url], [30, 25, 20, 8, 9, 8])[0]
        return f(self.rng)

    def prose_runs(self, p_value: float = 0.35, min_words: int = 6, max_words: int = 40) -> list[Run]:
        s = self.pool.sentence(self.rng, min_words, max_words)
        return self.with_value(s, self.value()) if self.rng.random() < p_value else [Run(s)]

    def footnote(self, p: Paragraph | Heading, kind: str = "footnote") -> None:
        n = Note(id=self.id("n"), kind=kind, paragraphs=[self.para([Run(self.pool.sentence(self.rng, 5, 25))])])
        self.notes.append(n)
        p.notes.append(NoteAnchor(n.id, len(text_of(p))))

    def meta(self, template: str, look: str, font: str | None = None) -> Meta:
        return Meta(template=template, look=look, seed=self.seed, font=font or self.rng.choice(OPEN_FONTS),
                    font_size_pt=self.rng.choice([10.0, 11.0, 12.0]), text_sources=self.pool.sources())


def section_numbering() -> AbstractNum:
    return AbstractNum(1, [Level("decimal", "%1."), Level("decimal", "%1.%2."), Level("decimal", "%1.%2.%3."),
                           Level("hebrew1", "(%4)")])


def bullet_numbering() -> AbstractNum:
    return AbstractNum(2, [Level("bullet", "•"), Level("bullet", "–")])


def table_from_rows(b: Builder, rows: list[list[str | list[Run]]], header_rows: int = 1,
                    merges: dict[tuple[int, int], tuple[int, int]] | None = None, **kw) -> Table:
    """A table from a full grid of texts; `merges` maps a cell's (r, c) to its (rowspan, colspan). Covered slots in
    `rows` are ignored."""
    merges = merges or {}
    n_rows, n_cols = len(rows), len(rows[0])
    covered: set[tuple[int, int]] = set()
    for (r, c), (rs, cs) in merges.items():
        covered |= {(rr, cc) for rr in range(r, r + rs) for cc in range(c, c + cs)} - {(r, c)}
    cells = []
    for r in range(n_rows):
        for c in range(n_cols):
            if (r, c) in covered:
                continue
            v = rows[r][c]
            runs = v if isinstance(v, list) else ([Run(v, "num" if _numeric(v) else "he")] if v else [])
            rs, cs = merges.get((r, c), (1, 1))
            cells.append(Cell(r=r, c=c, rowspan=rs, colspan=cs, header=r < header_rows,
                              paragraphs=[b.para(runs)]))
    return Table(id=b.id("t"), rows=n_rows, cols=n_cols, cells=cells, **kw)


def _numeric(s: str) -> bool:
    return bool(s) and all(ch.isdigit() or ch in ".,%₪/- " for ch in s) and any(ch.isdigit() for ch in s)


def build(template: str, doc_id: str, seed: int, pool: TextPool) -> Document:
    from . import report, tables, tender
    return {"tender": tender.build, "report": report.build, "tables": tables.build}[template](doc_id, seed, pool)


TEMPLATES = ("tender", "report", "tables")
