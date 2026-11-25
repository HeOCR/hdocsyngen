"""Replay PDF readers on an existing synthetic pilot without rerunning producers."""
from __future__ import annotations

from collections import Counter
from hashlib import file_digest, sha256
from importlib.metadata import version
import json
from pathlib import Path
import subprocess

from .pdfcheck import read_text_layer
from .tree import loads

_READERS = ("pdfminer", "poppler", "pymupdf")


def _sha(path: Path) -> str:
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def _owned_file(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Missing or out-of-scope pilot file: {Path(name).name}")
    return path


def _pdf_from_receipt(root: Path, receipt: dict, expected_version: str, *,
                      build: dict | None = None, input_sha256: str | None = None) -> Path:
    build = {"version": expected_version} if build is None else build
    if any(receipt.get(key) != value for key, value in build.items()):
        raise ValueError("Producer version or build differs from the pilot pin")
    if input_sha256 is not None and receipt.get("input_sha256") != input_sha256:
        raise ValueError("Producer input differs from the pilot source digest")
    asset = receipt["outputs"]["pdf"]
    path = _owned_file(root, asset["path"])
    if _sha(path) != asset["sha256"]:
        raise ValueError(f"PDF differs from the producer receipt: {path.name}")
    return path


def _metadata_version_matches(pdf: Path, pinned_version: str) -> bool:
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(str(pdf)) as document:
        producer = document.get_metadata_value("Producer")
    # LibreOffice names its release in the PDF but the build SHA is in the run manifest.
    release = " ".join(pinned_version.split()[:2])
    return producer == release or producer.startswith(release + " ")


def _counts(audit: dict) -> dict:
    pages = audit["pages"]
    out = {"pages": len(pages), "pdfium_visual_chars": sum(p["pdfium_visual_chars"] for p in pages)}
    out["readers"] = {
        reader: {
            "missing": sum(p["readers"][reader]["missing"] for p in pages),
            "extra": sum(p["readers"][reader]["extra"] for p in pages),
            "order": dict(Counter(p["reader_order"][reader] for p in pages)),
        }
        for reader in _READERS
    }
    if "ltr_slots" in audit:
        blocks = audit["ltr_slots"].values()
        out["ltr_slots"] = {
            **{kind: sum(block[kind] for block in blocks) for kind in ("forward", "reversed", "unresolved")},
            "visual_lines_compared": sum("visual_order" in block for block in blocks),
            **{
                reader + "_agree": sum(block.get("visual_order", {}).get(reader, False) for block in blocks)
                for reader in ("python_bidi", "rust_bidi")
            },
        }
    return out


def run(root: Path) -> dict:
    """Return counts and file pins for every producer slot in a saved pilot."""
    root = root.resolve()
    manifest_path = _owned_file(root, "manifest.json")
    manifest = json.loads(manifest_path.read_bytes())
    if manifest["schema"] != "hdocsyngen_pilot.v0" or manifest["versions"] != manifest["versions_after"]:
        raise ValueError("Pilot manifest is unsupported or its producer versions changed")
    versions = {key: value for key, value in manifest["versions"].items() if value is not None}
    builds = manifest.get("producer_builds")
    if builds is not None and (builds != manifest.get("producer_builds_after")
                               or {k: v["version"] for k, v in builds.items()} != versions
                               or ("word" in builds and not builds["word"].get("bundle_version"))):
        raise ValueError("Pilot build pins changed or are incomplete")
    entries = manifest["docs"]
    if len({entry["doc_id"] for entry in entries}) != len(entries):
        raise ValueError("Duplicate document IDs in pilot manifest")

    poppler = subprocess.run(["pdftotext", "-v"], check=True, capture_output=True, text=True, timeout=30)
    import pypdfium2 as pdfium

    rows = []
    for entry in entries:
        doc_id = entry["doc_id"]
        result_path = _owned_file(root, entry["result"])
        result_bytes = result_path.read_bytes()
        result_sha = sha256(result_bytes).hexdigest()
        if (builds is not None or "result_sha256" in entry) and entry.get("result_sha256") != result_sha:
            raise ValueError(f"Result record differs from the pilot manifest: {doc_id}")
        result = json.loads(result_bytes)
        tree_path = _owned_file(result_path.parent, f"{doc_id}.tree.json")
        tree_bytes = tree_path.read_bytes()
        tree_sha = sha256(tree_bytes).hexdigest()
        if result["sources"].get("tree.json") != tree_sha:
            raise ValueError(f"Source tree differs from the producer result: {doc_id}")
        tree = loads(tree_bytes.decode("utf-8"))
        if doc_id != result["doc_id"] or doc_id != tree.doc_id or set(result["producers"]) != set(versions):
            raise ValueError(f"Tree, producer roster, or result identity differs: {doc_id}")
        for producer, pinned_version in versions.items():
            result_row = result["producers"][producer]
            folder = (result_path.parent / producer).resolve()
            if not folder.is_relative_to(result_path.parent):
                raise ValueError(f"Producer directory outside its pilot document: {doc_id}")
            row = {"doc_id": doc_id, "producer": producer, "producer_version": pinned_version,
                   "tree_sha256": tree_sha, "producer_result_sha256": result_sha}
            if "error" not in result_row:
                build = builds[producer] if builds else None
                ext = "html" if producer == "chrome" else "docx"
                source = result["sources"]
                plain = _pdf_from_receipt(folder, result_row["plain"], pinned_version, build=build,
                                          input_sha256=source[ext])
                twin = _pdf_from_receipt(folder, result_row["twin"], pinned_version, build=build,
                                         input_sha256=source[f"twin.{ext}"])
                if build and producer == "word":
                    row["producer_bundle_version"] = build["bundle_version"]
                row.update(status="paired",
                           version_basis="per_document_plain_and_twin_receipts",
                           plain_sha256=_sha(plain), twin_sha256=_sha(twin),
                           **_counts(read_text_layer(plain, tree, twin)))
            else:
                # Historical LibreOffice TXT failures may leave the plain PDF before the receipt is written.
                saved = folder / f"{doc_id}.{producer}.pdf"
                if builds is None and producer == "lo" and saved.is_file():
                    plain = _owned_file(folder, saved.name)
                    if not _metadata_version_matches(plain, pinned_version):
                        raise ValueError(f"Partial PDF producer metadata does not match the pilot pin: {doc_id}")
                    row.update(status="plain_only_after_producer_error",
                               version_basis="run_pin_and_pdf_release_metadata",
                               plain_sha256=_sha(plain), **_counts(read_text_layer(plain)))
                else:
                    row.update(status="producer_error", version_basis="run_pin_only")
            rows.append(row)
    return {
        "schema": "hdocsyngen_pilot_readback.v1",
        "pilot_manifest_sha256": _sha(manifest_path),
        "producer_versions": versions,
        "reader_versions": {
            "pypdfium2": version("pypdfium2"), "pdfium": str(pdfium.PDFIUM_INFO),
            "pdfminer.six": version("pdfminer.six"), "pymupdf": version("PyMuPDF"),
            "poppler": (poppler.stderr or poppler.stdout).splitlines()[0],
            "python-bidi": version("python-bidi"),
        },
        "documents": len(entries),
        "rows": rows,
    }
