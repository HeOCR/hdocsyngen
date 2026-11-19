"""Gold checks for DOCX outputs (our writer's, or a producer's re-saved DOCX): design note §2 and §3.3.

`verify_docx(doc, data)` reads the file with the independent reader and checks it against the tree: body block order
and text, table grids, numPr references, note anchors and texts, header and footer text. Field results are not
checked (producer-filled). An empty list means the DOCX carries the gold.
"""
from __future__ import annotations

from .readers.docx_read import read
from .tree import Document, Heading, PageBreak, Paragraph, Table, text_of


def _expected_body(doc: Document):
    for b in doc.body:
        if isinstance(b, PageBreak):
            continue
        yield b


def verify_docx(doc: Document, data: bytes, check_numbering: bool = True) -> list[str]:
    got = read(data)
    problems: list[str] = []
    blocks = [b for b in got["blocks"] if not (b["type"] == "p" and not b["text"] and not b["notes"] and b["num"] is None)]
    expected = list(_expected_body(doc))
    if len(blocks) != len(expected):
        problems.append(f"body: {len(blocks)} blocks read, {len(expected)} expected")
    note_seq_got, note_seq_exp = [], []
    num_map: dict[int, int] = {}
    rev_map: dict[int, int] = {}
    note_kind = {n.id: n.kind for n in doc.notes}
    note_text = {n.id: "\n".join(text_of(p) for p in n.paragraphs) for n in doc.notes}
    for i, (e, g) in enumerate(zip(expected, blocks)):
        if isinstance(e, Table):
            if g["type"] != "table":
                problems.append(f"{e.id}: expected a table, read a paragraph")
                continue
            exp_cells = {(c.r, c.c, c.rowspan, c.colspan, "\n".join(text_of(p) for p in c.paragraphs))
                         for c in e.cells}
            got_cells = {(c["r"], c["c"], c["rowspan"], c["colspan"], c["text"]) for c in g["cells"]}
            if (g["rows"], g["cols"]) != (e.rows, e.cols):
                problems.append(f"{e.id}: grid {g['rows']}x{g['cols']}, expected {e.rows}x{e.cols}")
            for miss in sorted(exp_cells - got_cells)[:5]:
                problems.append(f"{e.id}: cell {miss[:4]} not read as expected")
            for c in sorted(e.cells, key=lambda c: (c.r, c.c)):
                for p in c.paragraphs:
                    note_seq_exp += [(i, a.offset, note_kind[a.note_id], note_text[a.note_id]) for a in p.notes]
            for c in sorted(g["cells"], key=lambda c: (c["r"], c["c"])):
                for p in c["paragraphs"]:
                    note_seq_got += [(i, n["offset"], n["kind"], n["w_id"]) for n in p["notes"]]
            continue
        if g["type"] != "p":
            problems.append(f"{e.id}: expected a paragraph, read a table")
            continue
        if g["text"] != text_of(e):
            problems.append(f"{e.id}: text differs")
        if check_numbering:
            # Producers renumber numIds when they re-save, so ids are compared as a consistent one-to-one mapping;
            # levels must match exactly.
            exp_num = (e.num.num_id, e.num.level) if e.num else None
            if (g["num"] is None) != (exp_num is None):
                problems.append(f"{e.id}: numPr {g['num']}, expected {exp_num}")
            elif exp_num is not None:
                gid, glvl = g["num"]
                if glvl != exp_num[1]:
                    problems.append(f"{e.id}: list level {glvl}, expected {exp_num[1]}")
                if num_map.setdefault(gid, exp_num[0]) != exp_num[0] or rev_map.setdefault(exp_num[0], gid) != gid:
                    problems.append(f"{e.id}: list {gid} does not map one-to-one to num {exp_num[0]}")
        note_seq_exp += [(i, a.offset, note_kind[a.note_id], note_text[a.note_id]) for a in e.notes]
        note_seq_got += [(i, n["offset"], n["kind"], n["w_id"]) for n in g["notes"]]
    texts = {"footnote": got["footnotes"], "endnote": got["endnotes"]}
    resolved = [(i, off, kind, texts[kind].get(wid)) for i, off, kind, wid in note_seq_got]
    if resolved != note_seq_exp:
        problems.append(f"notes: {len(resolved)} anchors read, {len(note_seq_exp)} expected, or anchor/text differs")
    for kind in ("header", "footer"):
        exp = [text_of(p) for p in getattr(doc.furniture, kind)]
        if got["furniture"][kind] != exp:
            problems.append(f"{kind}: text differs")
    return problems
