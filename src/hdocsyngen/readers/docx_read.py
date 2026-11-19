"""An independent DOCX reader, used only to verify writers and producer-re-saved DOCX against the gold.

It is deliberately small and shares no code with the writers or with `heocr`. It reads the body (paragraphs and
tables, with gridSpan and vMerge), footnotes, endnotes, the default header and footer, and numPr references. Field
results (simple and complex fields) are skipped, as the gold leaves field text to the producer.
"""
from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _para(p: ET.Element) -> dict:
    """Text, numPr and note references of one w:p, in document order."""
    text, notes = [], []
    in_field = 0
    num = None
    ppr = p.find(f"{W}pPr")
    if ppr is not None:
        np_ = ppr.find(f"{W}numPr")
        if np_ is not None and np_.find(f"{W}numId") is not None:
            ilvl = np_.find(f"{W}ilvl")
            num = (int(np_.find(f"{W}numId").get(f"{W}val")), int(ilvl.get(f"{W}val")) if ilvl is not None else 0)

    def walk(el: ET.Element, skip: bool):
        nonlocal in_field
        for ch in el:
            tag = ch.tag
            if tag == f"{W}fldSimple":
                continue                                  # field result: producer-filled
            if tag == f"{W}fldChar":
                t = ch.get(f"{W}fldCharType")
                if t == "begin":
                    in_field += 1
                elif t == "end":
                    in_field = max(0, in_field - 1)
                continue
            if tag == f"{W}t" and not skip and not in_field:
                text.append(ch.text or "")
            elif tag == f"{W}tab" and not skip and not in_field:
                text.append("\t")
            elif tag in (f"{W}footnoteReference", f"{W}endnoteReference"):
                kind = "footnote" if tag == f"{W}footnoteReference" else "endnote"
                notes.append({"kind": kind, "w_id": int(ch.get(f"{W}id")), "offset": len("".join(text))})
            elif tag in (f"{W}pPr", f"{W}rPr", f"{W}instrText", f"{W}delText"):
                continue
            else:
                walk(ch, skip)

    walk(p, False)
    return {"text": "".join(text), "num": num, "notes": notes}


def _table(tbl: ET.Element) -> dict:
    rows = tbl.findall(f"{W}tr")
    n_cols = len(tbl.find(f"{W}tblGrid").findall(f"{W}gridCol"))
    cells, open_v = [], {}                                # open_v: grid column -> cell dict (vertical merge)
    for r, tr in enumerate(rows):
        c = 0
        for tc in tr.findall(f"{W}tc"):
            tcpr = tc.find(f"{W}tcPr")
            span, vmerge = 1, None
            if tcpr is not None:
                gs = tcpr.find(f"{W}gridSpan")
                span = int(gs.get(f"{W}val")) if gs is not None else 1
                vm = tcpr.find(f"{W}vMerge")
                if vm is not None:
                    vmerge = vm.get(f"{W}val", "continue")
            paras = [_para(p) for p in tc.findall(f"{W}p")]
            if vmerge == "continue" and c in open_v:
                open_v[c]["rowspan"] += 1
            else:
                cell = {"r": r, "c": c, "rowspan": 1, "colspan": span, "paragraphs": paras,
                        "text": "\n".join(p["text"] for p in paras)}
                cells.append(cell)
                if vmerge == "restart":
                    open_v[c] = cell
                else:
                    open_v.pop(c, None)
            c += span
    return {"type": "table", "rows": len(rows), "cols": n_cols, "cells": cells}


def _notes(z: zipfile.ZipFile, name: str, kind: str) -> dict[int, str]:
    if name not in z.namelist():
        return {}
    root = ET.fromstring(z.read(name))
    out = {}
    for n in root.findall(f"{W}{kind}"):
        if n.get(f"{W}type") in ("separator", "continuationSeparator", "continuationNotice"):
            continue
        texts = [_para(p)["text"] for p in n.findall(f"{W}p")]
        if texts:
            texts[0] = texts[0][1:] if texts[0].startswith(" ") else texts[0]
        out[int(n.get(f"{W}id"))] = "\n".join(texts)
    return out


def read(data: bytes) -> dict:
    z = zipfile.ZipFile(io.BytesIO(data))
    root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(f"{W}body")
    blocks = []
    for el in body:
        if el.tag == f"{W}p":
            blocks.append({"type": "p", **_para(el)})
        elif el.tag == f"{W}tbl":
            blocks.append(_table(el))
    rels = ET.fromstring(z.read("word/_rels/document.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels}
    furniture = {"header": [], "footer": []}
    sect = body.find(f"{W}sectPr")
    if sect is not None:
        for kind, tag in (("header", "headerReference"), ("footer", "footerReference")):
            for ref in sect.findall(f"{W}{tag}"):
                if ref.get(f"{W}type", "default") == "default":
                    part = ET.fromstring(z.read("word/" + target[ref.get(f"{R}id")]))
                    furniture[kind] = [_para(p)["text"] for p in part.findall(f"{W}p")]
    return {"blocks": blocks, "footnotes": _notes(z, "word/footnotes.xml", "footnote"),
            "endnotes": _notes(z, "word/endnotes.xml", "endnote"), "furniture": furniture}
