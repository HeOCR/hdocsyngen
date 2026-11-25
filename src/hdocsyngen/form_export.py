"""Export the forms of an `hdoc_gold.v1` document as `hdoc_form.v1`, the form format heocr-bench's form scorers read.

`hdoc_form.v1` (docs/tables_forms_design.md, "Schema additions"): `form → section* → (field | table | group)`.

- **Field:** `{type, id, label, value, kind, slot, pages}`. The label and value are as printed, and an unfilled
  field's value is `""`. A checkbox's value is `checked` or `unchecked`; a choice's is the marked option's text.
- **Table:** the table as `heocr_table.v1` (`table_export.to_heocr_table`).
- **Group:** `{type, columns}`, layout only (fields side by side).

Pages come from a producer layer's block pages: a field's pages are those of the paragraphs that print it, and a
section's pages are the union over its children. Without a producer layer they are `null`. The tree's internal
references (`paragraphs`, `heading`) are left out of the export.
"""
from __future__ import annotations

from .table_export import to_heocr_table

SCHEMA = "hdoc_form.v1"


def _pages(ids: list[str], pages: dict[str, list[int]] | None) -> list[int] | None:
    if pages is None:
        return None
    found = sorted({p for i in ids for p in pages.get(i, [])})
    return found or None


def _children(children: list[dict], tables: dict, pages) -> tuple[list[dict], list[str]]:
    out, ids = [], []
    for ch in children:
        if ch["type"] == "field":
            out.append({"type": "field", "id": ch["id"], "label": ch["label"], "value": ch["value"],
                        "kind": ch["kind"], "slot": ch["slot"], "pages": _pages(ch["paragraphs"], pages)})
            ids += ch["paragraphs"]
        elif ch["type"] == "table":
            t = tables[ch["table"]]
            cell_ids = [pid for c in t["cells"] for pid in c.get("paragraphs", [])]
            out.append({"type": "table", "table": to_heocr_table(t, _pages(cell_ids, pages))})
            ids += cell_ids
        elif ch["type"] == "group":
            columns = []
            for column in ch["columns"]:
                kids, kid_ids = _children(column, tables, pages)
                columns.append(kids)
                ids += kid_ids
            out.append({"type": "group", "columns": columns})
        elif ch["type"] == "section":
            section, kid_ids = _section(ch, tables, pages)
            out.append(section)
            ids += kid_ids
    return out, ids


def _section(section: dict, tables: dict, pages) -> tuple[dict, list[str]]:
    children, ids = _children(section["children"], tables, pages)
    if section.get("heading"):
        ids = [section["heading"], *ids]
    return {"type": "section", "title": section.get("title"), "children": children, "pages": _pages(ids, pages)}, ids


def export(gold: dict, producer_gold: dict | None = None) -> list[dict]:
    """All forms of a gold document. With a producer layer (`blocks` carrying `pages`), pages are filled in."""
    tables = {t["id"]: t for t in gold.get("tables", [])}
    pages = None
    if producer_gold is not None:
        pages = {b["id"]: b["pages"] for b in producer_gold.get("blocks", []) if b.get("pages")}
    out = []
    for form in gold.get("forms", []):
        sections = [_section(s, tables, pages)[0] for s in form["sections"]]
        out.append({"schema": SCHEMA, "id": form["id"], "title": form["title"], "direction": "rtl",
                    "sections": sections})
    return out
