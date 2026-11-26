"""Audit the PDF text and structure of tables and forms in a saved native pilot."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from . import form_export, pilot_readback, table_export
from .gold import gold as tree_gold
from .pilot_lines import physical_lines
from .pilot_readback import _owned_file, _pdf_from_receipt, _sha
from .tree import form_fields, loads
from .verify import verify_docx


def _structure(gold: dict, lines: list[dict]) -> dict:
    """Project verified physical paragraph pages into the existing 0032 exports."""
    pages_by_block = defaultdict(set)
    for line in lines:
        pages_by_block[line["block_id"]].add(line["page"])
    observed = {"blocks": [{"id": ident, "pages": sorted(pages)} for ident, pages in pages_by_block.items()]}
    tables = []
    for table in gold["tables"]:
        pages_by_row = defaultdict(set)
        table_pages = set()
        h = table_export.header_rows(table)
        for cell in table["cells"]:
            pages = {page for p in cell["paragraphs"] for page in pages_by_block[p]}
            if cell["text"].strip() and not pages:
                raise ValueError(f"Missing printed text for cell {table['id']}:{cell['r']}:{cell['c']}")
            table_pages.update(pages)
            if cell["r"] >= h:
                pages_by_row[cell["r"]].update(pages)
        if not table_pages:
            raise ValueError(f"Table has no physical text anchors: {table['id']}")
        if any(len(pages) > 1 for pages in pages_by_row.values()):
            raise ValueError(f"Body row split across pages: {table['id']}")
        body_pages = [next(iter(pages)) for _, pages in sorted(pages_by_row.items()) if pages]
        if body_pages != sorted(body_pages):
            raise ValueError(f"Logical table rows are out of page order: {table['id']}")
        expected_header = table_pages if table["repeat_header"] else {min(table_pages)}
        for cell in table["cells"]:
            if cell["r"] < h:
                pages = {page for p in cell["paragraphs"] for page in pages_by_block[p]}
                if cell["text"].strip() and pages != expected_header:
                    raise ValueError(f"Header copy is missing or unexpected: {table['id']}:{cell['r']}:{cell['c']}")
        record = table_export.to_heocr_table(table, sorted(table_pages))
        record["page_breaks"] = table_export.page_breaks(table, observed)
        tables.append(record)
    for form in gold.get("forms", []):
        for section in form["sections"]:
            for field in form_fields(section["children"]):
                if not any(pages_by_block[ident] for ident in field["paragraphs"]):
                    raise ValueError(f"Form field has no physical text anchor: {field['id']}")
    return {"tables": tables, "forms": form_export.export(gold, observed)}


def _readers(check: dict) -> None:
    if any(row["missing"] or row["extra"] for row in check["readers"].values()):
        raise ValueError("Independent reader glyph inventory differs from PDFium")
    if check["ltr_slots"]["reversed"]:
        raise ValueError("Left-to-right token is reversed in the physical slots")


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def run(root: Path, output: Path) -> dict:
    """Write one physical line and structure record per accepted PDF and a counts manifest."""
    root = root.resolve()
    manifest_path = _owned_file(root, "manifest.json")
    manifest = json.loads(manifest_path.read_bytes())
    readback = pilot_readback.run(root)
    counts = {(item["doc_id"], item["producer"]): item for item in readback["rows"]}
    builds = manifest["producer_builds"]
    output.mkdir(mode=0o700)
    rows = []
    for item in manifest["docs"]:
        ident = item["doc_id"]
        result_path = _owned_file(root, item["result"])
        result = json.loads(result_path.read_bytes())
        tree_path = _owned_file(result_path.parent, f"{ident}.tree.json")
        raw_tree = tree_path.read_text(encoding="utf-8")
        tree = loads(raw_tree)
        expected = tree_gold(tree, raw_tree)
        docx = _owned_file(result_path.parent, f"{ident}.docx")
        if _sha(docx) != result["sources"]["docx"]:
            raise ValueError("Saved source DOCX differs from the pilot input")
        docx_problems = verify_docx(tree, docx.read_bytes())
        for route, build in builds.items():
            lane = result["producers"][route]
            check = counts[ident, route]
            row = {"doc_id": ident, "producer": route, "producer_version": build["version"],
                   "tree_sha256": check["tree_sha256"]}
            if route == "word":
                row["producer_bundle_version"] = build["bundle_version"]
            rows.append(row)
            if check["status"] != "paired" or lane["pdf_check"]["problems"] or docx_problems:
                row.update(status="hold", reason="native_producer_check",
                           native_problems=lane.get("pdf_check", {}).get("problems", []) + docx_problems)
                continue
            ext = "html" if route == "chrome" else "docx"
            for suffix in (ext, f"twin.{ext}"):
                if _sha(_owned_file(result_path.parent, f"{ident}.{suffix}")) != result["sources"][suffix]:
                    raise ValueError("Saved writer input differs from the producer receipt")
            plain, twin = (
                _pdf_from_receipt(result_path.parent / route, lane[mode], build["version"], build=build,
                                  input_sha256=result["sources"][prefix + ext])
                for mode, prefix in (("plain", ""), ("twin", "twin."))
            )
            gold_path = _owned_file(result_path.parent, f"{ident}.{route}.gold.json")
            gold = json.loads(gold_path.read_bytes())
            if (gold["lineage"]["tree_sha256"] != check["tree_sha256"]
                    or gold["producer"]["pdf_sha256"] != check["plain_sha256"]
                    or any(gold.get(part, []) != expected.get(part, []) for part in ("tables", "forms"))):
                raise ValueError("Structural gold is outside the pinned producer slot")
            resaved_problems = []
            resaved = lane["plain"]["outputs"].get("docx")
            if resaved:
                resaved_path = _owned_file(result_path.parent / route, resaved["path"])
                if _sha(resaved_path) != resaved["sha256"]:
                    raise ValueError("Resaved DOCX differs from its producer receipt")
                resaved_problems = verify_docx(tree, resaved_path.read_bytes())
            row.update(pdf_sha256=check["plain_sha256"], twin_sha256=check["twin_sha256"],
                       gold_sha256=_sha(gold_path), readers=check["readers"], ltr_slots=check["ltr_slots"],
                       resaved_docx_problems=resaved_problems)
            try:
                if not gold["tables"] and not gold.get("forms"):
                    raise ValueError("Source has no tables or forms")
                _readers(check)
                lines = physical_lines(tree, plain, twin, gold, check["plain_sha256"])
                if {line["page"] for line in lines} != set(range(1, check["pages"] + 1)):
                    raise ValueError("Physical references do not cover every PDF page")
                structure = _structure(gold, lines)
            except ValueError as exc:
                row.update(status="hold", reason=str(exc))
                continue
            name = f"{ident}.{route}.structure.json"
            sidecar = output / name
            _write(sidecar, {
                "schema": "hdocsyngen.native_structure.v1",
                "doc_id": ident, "pdf_sha256": check["plain_sha256"], "tree_sha256": check["tree_sha256"],
                "producer": route, "producer_build": build, "lines": lines, **structure,
            })
            row.update(status="pass", pages=check["pages"], lines=len(lines),
                       tables=len(structure["tables"]), forms=len(structure["forms"]),
                       continuation_tables=sum(len(t["pages"]) > 1 for t in structure["tables"]),
                       sidecar=name, sidecar_sha256=_sha(sidecar))
    result = {
        "schema": "hdocsyngen.native_structure_audit.v1",
        "pilot_manifest_sha256": _sha(manifest_path),
        "reader_versions": readback["reader_versions"], "producer_builds": builds,
        "rows": rows, "expected_slots": len(rows),
        "verified_slots": sum(row["status"] == "pass" for row in rows),
    }
    _write(output / "manifest.json", result)
    return result
