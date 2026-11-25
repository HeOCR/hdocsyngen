"""Word, LibreOffice and local Chrome pilot with exact per-page source gold."""
from __future__ import annotations

from collections import Counter
from hashlib import file_digest
import json
from pathlib import Path
import re

from . import producers
from .fonts import EXCLUSION_PATH, Registry
from .literal_verify import declared_glyphs, literal, reader_versions, source_pages, verify_pdf
from .page_verify import body_columns, verify_page
from .tree import loads, text_of
from .writers import docx, html

NATIVE = ("word", "lo", "chrome")


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def _write(path: Path, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(data, encoding="utf-8")


def _versions():
    return {
        "word": {"version": producers.word_version(), "bundle_version": producers.word_bundle_version()},
        "lo": {"version": producers.lo_version()},
        "chrome": {"version": producers.chrome_version()},
    }


def run(tree_root: Path, font_dirs: list[Path], output: Path, layout_plan: Path | None = None,
        *, routes: tuple[str, ...] = NATIVE) -> dict:
    """Run all three producers for every tree, and emit page GT from verified PDFs."""
    if not routes or len(set(routes)) != len(routes) or set(routes) - set(NATIVE):
        raise ValueError("Unknown or repeated native producer routes")
    tree_paths = sorted(tree_root.glob("*.json"))
    if not tree_paths:
        raise ValueError("No source tree JSON files found")
    plan = json.loads(layout_plan.read_bytes()) if layout_plan else None
    registry = Registry.scan(font_dirs)
    trees = []
    seen = set()
    for path in tree_paths:
        source = path.read_bytes()
        tree = loads(source.decode("utf-8"))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", tree.doc_id) or tree.doc_id in seen:
            raise ValueError("Unsafe or duplicate document ID")
        seen.add(tree.doc_id)
        second_column_at = None
        if plan is not None:
            second_column_at = plan[tree.doc_id]
            pages = body_columns(tree, second_column_at)
            pages += [tree.furniture.header, tree.furniture.footer, *(note.paragraphs for note in tree.notes)]
        else:
            pages = source_pages(tree)
        faces = tuple(font for font in registry.files if font.family == tree.meta.font)
        declared = declared_glyphs(tree.meta.font, faces)
        if set(literal("".join(text_of(block) for page in pages for block in page))) - set().union(*declared.values()):
            raise ValueError(f"{tree.doc_id}: declared font coverage is incomplete")
        trees.append((tree, source, faces, second_column_at))

    if plan is not None and set(plan) != seen:
        raise ValueError("Layout plan and tree IDs differ")
    versions = _versions()
    readers = reader_versions()
    output.mkdir(mode=0o700)
    rows = []
    failures = []
    for tree, source, faces, second_column_at in trees:
        folder = output / tree.doc_id
        folder.mkdir(mode=0o700)
        source_path = folder / f"{tree.doc_id}.tree.json"
        source_path.write_bytes(source)
        docx_path = folder / f"{tree.doc_id}.docx"
        docx_path.write_bytes(docx.write(tree, page_layout=plan is not None, second_column_at=second_column_at))
        html_path = folder / f"{tree.doc_id}.html"
        html_path.write_bytes(html.write(tree, embedded_fonts=faces, page_layout=plan is not None,
                                        second_column_at=second_column_at))
        calls = {
            "word": (producers.word_convert, docx_path, {"outputs": ("pdf",)}),
            "lo": (producers.lo_convert, docx_path, {"outputs": ("pdf",)}),
            "chrome": (producers.chrome_convert, html_path, {}),
        }
        for route in routes:
            convert, render_source, opts = calls[route]
            try:
                receipt = convert(render_source, folder.resolve(), **opts)
                if any(receipt[k] != pin for k, pin in versions[route].items()):
                    raise producers.VersionChanged(f"{route} version differs from the run pin")
                pdf = folder / receipt["outputs"]["pdf"]["path"]
                audit = (verify_page(pdf, tree, faces, second_column_at) if plan is not None
                         else verify_pdf(pdf, tree, faces))
                if audit["pdf_sha256"] != receipt["outputs"]["pdf"]["sha256"] or not audit["pdf_producer_signature"]:
                    raise ValueError("Missing PDF producer signature or PDF changed during verification")
            except (producers.VersionChanged, KeyboardInterrupt):
                raise
            except (producers.ProducerError, ValueError) as exc:
                failures.append({"doc_id": tree.doc_id, "producer": route, "reason": str(exc)})
                _write(output / "failures.json", {"failures": failures})
                continue
            gt = pdf.with_suffix(".pages.json")
            record = {
                "doc_id": tree.doc_id,
                "tree_sha256": _sha(source_path),
                "fonts": registry.manifest(tree.meta.font),
                "font_family": tree.meta.font,
                "producer": receipt,
                "reader_versions": readers,
                **audit,
            }
            _write(gt, record)
            rows.append({
                "doc_id": tree.doc_id, "producer": route, "version": receipt["version"],
                "pdf_producer_signature": audit["pdf_producer_signature"],
                "tree_sha256": record["tree_sha256"], "pdf_sha256": audit["pdf_sha256"],
                "pdf": pdf.relative_to(output).as_posix(), "page_gt": gt.relative_to(output).as_posix(),
                "page_gt_sha256": _sha(gt), "pages": len(audit["pages"]),
                "lines": sum(len(page["lines"]) for page in audit["pages"]),
                "check_methods": dict(Counter(page["check_method"] for page in audit["pages"])),
            })
    if _versions() != versions:
        raise producers.VersionChanged("Native producer version changed during the pilot")
    result = {
        "schema": "hdocsyngen.native_pilot.v1",
        "font_exclusions_sha256": _sha(EXCLUSION_PATH),
        "producer_versions": versions,
        "reader_versions": readers,
        "trees": len(trees),
        "verified_slots": len(rows),
        "expected_slots": len(trees) * len(routes),
        "pages": sum(row["pages"] for row in rows),
        "rows": rows,
        "failures": failures,
    }
    if layout_plan:
        result["layout_plan_sha256"] = _sha(layout_plan)
    _write(output / "manifest.json", result)
    return result
