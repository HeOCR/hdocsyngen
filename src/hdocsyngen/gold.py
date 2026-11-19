"""The gold a source tree implies, before any producer touches it (design note §3.2).

Producer-dependent layers (pages, geometry, the `producer` label basis, `not_rendered`) are added later by the
verifier; this module writes only what the tree fixes exactly.
"""
from __future__ import annotations

from .numbering import model_labels
from .tree import Document, Heading, PageBreak, Paragraph, Table, text_of

GOLD_SCHEMA = "hdoc_gold.v1-draft"


def _value_spans(p: Paragraph | Heading) -> list[dict]:
    spans, pos = [], 0
    for r in p.runs:
        if r.field is not None:
            continue
        if r.kind is not None:
            spans.append({"kind": r.kind, "start": pos, "end": pos + len(r.text), "text": r.text})
        pos += len(r.text)
    return spans


def gold(doc: Document) -> dict:
    labels = model_labels(doc)
    blocks, order, tables = [], [], []

    def para_entry(p, parent: str | None, btype: str, level: int | None = None) -> dict:
        e = {"id": p.id, "type": btype, "text": text_of(p), "parent": parent}
        if level is not None:
            e["level"] = level
        if p.id in labels:
            e["label_model"] = labels[p.id]
        spans = _value_spans(p)
        if spans:
            e["values"] = spans
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
            tables.append({"id": b.id, "rows": b.rows, "cols": b.cols, "repeat_header": b.repeat_header,
                           "ruled": b.ruled, "cells": cells})
            blocks.append({"id": b.id, "type": "table", "parent": None})
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
        "header": [{"id": p.id, "text": text_of(p), "fields": [r.field for r in p.runs if r.field]}
                   for p in doc.furniture.header],
        "footer": [{"id": p.id, "text": text_of(p), "fields": [r.field for r in p.runs if r.field]}
                   for p in doc.furniture.footer],
    }
    return {"schema": GOLD_SCHEMA, "doc_id": doc.doc_id, "template": doc.meta.template, "look": doc.meta.look,
            "seed": doc.meta.seed, "text_sources": doc.meta.text_sources,
            "reading_order": order, "blocks": blocks, "tables": tables, "notes": notes, "furniture": furniture,
            "label_basis": "model"}
