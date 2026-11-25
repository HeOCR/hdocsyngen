"""The gold a source tree implies, before any producer touches it (design note §3.2).

Producer-dependent layers (pages, geometry, the `producer` label basis, `not_rendered`) are added later by the
verifier; this module writes only what the tree fixes exactly.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

from . import __version__
from .numbering import model_labels
from .layout import blocks_meta
from .tree import Document, Heading, PageBreak, Paragraph, Table, text_of

GOLD_SCHEMA = "hdoc_gold.v1"
# D-bench's number tokens (measures.NUM): digits with separators, and an optional percent sign.
NUM = re.compile(r"\d+(?:[.,/]\d+)*%?")


def _commit() -> str | None:
    """The hdocsyngen commit that writes the gold: HDOCSYNGEN_COMMIT, else the checkout's HEAD, else None."""
    if os.environ.get("HDOCSYNGEN_COMMIT"):
        return os.environ["HDOCSYNGEN_COMMIT"]
    try:
        r = subprocess.run(["git", "-C", str(Path(__file__).parent), "rev-parse", "HEAD"], capture_output=True,
                           text=True, timeout=10)
        return r.stdout.strip() or None
    except Exception:
        return None


def _ltr_runs(p) -> list[dict]:
    """Spans of runs with lang en or num (adjacent ones merged), offsets into the stored text."""
    out, pos = [], 0
    for r in p.runs:
        if r.field is not None:
            continue
        if r.lang in ("en", "num") and r.text:
            if out and out[-1]["end"] == pos:
                out[-1]["end"] = pos + len(r.text)
            else:
                out.append({"start": pos, "end": pos + len(r.text)})
        pos += len(r.text)
    return out


def _fields(p) -> list[dict]:
    out, pos = [], 0
    for r in p.runs:
        if r.field is not None:
            out.append({"kind": r.field, "offset": pos})
        else:
            pos += len(r.text)
    return out


def _value_spans(p: Paragraph | Heading) -> list[dict]:
    spans, pos = [], 0
    for r in p.runs:
        if r.field is not None:
            continue
        if r.kind is not None:
            spans.append({"kind": r.kind, "start": pos, "end": pos + len(r.text), "text": r.text,
                          "core": NUM.findall(r.text)})
        pos += len(r.text)
    return spans


def gold(doc: Document, tree_json: str | None = None) -> dict:
    """The gold. `tree_json` is the serialised tree the gold is computed from (for its sha256 in the lineage)."""
    labels = model_labels(doc)
    blocks, order, tables = [], [], []
    counters: dict[str, int] = {}

    def para_entry(p, parent: str | None, btype: str, level: int | None = None) -> dict:
        container = parent or "body"
        counters[container] = counters.get(container, -1) + 1
        e = {"id": p.id, "type": btype, "text": text_of(p), "parent": parent, "order": counters[container]}
        if level is not None:
            e["level"] = level
        if p.id in labels:
            e["label_model"] = labels[p.id]
        spans = _value_spans(p)
        if spans:
            e["values"] = spans
        ltr = _ltr_runs(p)
        if ltr:
            e["ltr_runs"] = ltr
        return e

    for b in doc.body:
        if isinstance(b, PageBreak):
            continue
        order.append(b.id)
        if isinstance(b, Heading):
            blocks.append(para_entry(b, None, "heading", b.level))
        elif isinstance(b, Paragraph):
            blocks.append(para_entry(b, None, "paragraph"))
        elif isinstance(b, Table):
            cells = []
            for c in sorted(b.cells, key=lambda c: (c.r, c.c)):
                cells.append({"r": c.r, "c": c.c, "rowspan": c.rowspan, "colspan": c.colspan, "header": c.header,
                              "text": "\n".join(text_of(p) for p in c.paragraphs),
                              "paragraphs": [p.id for p in c.paragraphs]})
                for p in c.paragraphs:
                    blocks.append(para_entry(p, b.id, "cell_paragraph"))
            entry = {"id": b.id, "rows": b.rows, "cols": b.cols, "repeat_header": b.repeat_header,
                     "ruled": b.ruled, "cells": cells}
            if b.blocks > 1:
                entry["blocks"] = blocks_meta(b)
            tables.append(entry)
            counters["body"] = counters.get("body", -1) + 1
            blocks.append({"id": b.id, "type": "table", "parent": None, "order": counters["body"]})
    anchors = {}
    for container_block in [*doc.body]:
        ps = []
        if isinstance(container_block, (Paragraph, Heading)):
            ps = [container_block]
        elif isinstance(container_block, Table):
            ps = [p for c in container_block.cells for p in c.paragraphs]
        for p in ps:
            for a in p.notes:
                anchors[a.note_id] = (p.id, a.offset)
    notes = []
    for n in doc.notes:
        for p in n.paragraphs:
            blocks.append(para_entry(p, n.id, "note_paragraph"))
        block_id, offset = anchors[n.id]
        notes.append({"id": n.id, "kind": n.kind, "anchor_block": block_id, "anchor_offset": offset,
                      "text": "\n".join(text_of(p) for p in n.paragraphs)})
    furniture = {
        "header": [{"id": p.id, "order": i, "text": text_of(p), "fields": _fields(p), "ltr_runs": _ltr_runs(p)}
                   for i, p in enumerate(doc.furniture.header)],
        "footer": [{"id": p.id, "order": i, "text": text_of(p), "fields": _fields(p), "ltr_runs": _ltr_runs(p)}
                   for i, p in enumerate(doc.furniture.footer)],
    }
    from .tree import dumps
    tj = tree_json if tree_json is not None else dumps(doc)
    lineage = {"tree_sha256": hashlib.sha256(tj.encode("utf-8")).hexdigest(), "hdocsyngen": __version__,
               "hdocsyngen_commit": _commit()}
    return {"schema": GOLD_SCHEMA, "doc_id": doc.doc_id, "template": doc.meta.template, "look": doc.meta.look,
            "seed": doc.meta.seed, "text_sources": doc.meta.text_sources,
            "reading_order": order, "blocks": blocks, "tables": tables, "notes": notes, "furniture": furniture,
            **({"forms": [dict(f) for f in doc.forms]} if doc.forms else {}),
            "label_basis": "model", "lineage": lineage}
