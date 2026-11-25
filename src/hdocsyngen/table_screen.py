"""Generation-time, digest-only screening of table text against a protected projection (as #20's pilot does).

A one-token table line (a number or a one-word label) often collides with a protected short whole-line key, so
table trees are screened before they are written, never by looking at protected plaintext:

1. a numeric cell that hits is redrawn in the same shape (whole number, one or two decimals, percentage, grouped);
2. a letters-only line that hits is replaced, everywhere it occurs in the tree (a matrix repeats its names as
   diagonal labels), by a pool phrase of the same word count that clears every key;
3. ``PilotFilter.prepare`` then repairs furniture and checks every paragraph and whole cell.

``screen`` returns False when a tree cannot be cleared; the caller drops it or rebuilds it with the next seed.
"""
from __future__ import annotations

import random
import re

from .pilot_filter import PilotFilter
from .textpool import TextPool
from .tree import Document, Run, Table, iter_paragraphs, text_of

TRIES = 64
_NUMBER = re.compile(r"^\d[\d,]*(\.\d+)?%?$")


def _redraw_number(value: str, rng: random.Random) -> str:
    pct = value.endswith("%")
    core = value[:-1] if pct else value
    places = len(core.split(".")[1]) if "." in core else 0
    if "," in core:
        out = f"{rng.randrange(1_000, 9_999_999):,}"
    elif places:
        width = max(1, len(core.split(".")[0]))
        out = f"{rng.uniform(1, 10 ** width - 1):.{places}f}"
        if places == 1 and core.endswith((".0", ".5")):  # keep half steps half steps
            out = f"{rng.randrange(2, 2 * 10 ** width) / 2:.1f}"
    else:
        out = str(rng.randrange(1 if len(core) == 1 else 10 ** (len(core) - 1), 10 ** len(core)))
    return out + ("%" if pct else "")


def screen(doc: Document, guard: PilotFilter, pool: TextPool, rng: random.Random) -> bool:
    replaced: dict[str, str] = {}
    for _, para in iter_paragraphs(doc):
        text = text_of(para)
        if not text.strip() or not guard.hits(text):
            continue
        if _NUMBER.match(text.strip()):
            for _ in range(TRIES):
                candidate = _redraw_number(text.strip(), rng)
                if not guard.hits(candidate):
                    para.runs = [Run(candidate, "num")]
                    break
            else:
                return False
            continue
        if any(ch.isdigit() for ch in text):
            continue  # mixed text: left to prepare(), which rejects the tree if it still hits
        new = replaced.get(text)
        if new is None:
            n = len(text.split())
            for _ in range(TRIES):
                candidate = pool.phrase(rng, n, n)
                if candidate and not guard.hits(candidate) and candidate not in replaced.values():
                    new = candidate
                    break
            if new is None:
                continue  # prepare() may still clear it with a prefix
            replaced[text] = new
        para.runs = [Run(new, para.runs[0].lang if para.runs else "he")]
    # Every other occurrence of a replaced line, hit or not, so repeated names stay the same.
    for _, para in iter_paragraphs(doc):
        text = text_of(para)
        if text in replaced:
            para.runs = [Run(replaced[text], para.runs[0].lang if para.runs else "he")]
    return guard.prepare(doc)
