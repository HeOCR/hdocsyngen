"""Expand the saved pilot's three native producers through every implemented downstream route."""
from __future__ import annotations

from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile

from . import imagepdf, producers
from .pdfcheck import read_text_layer
from .pilot_readback import _counts, _owned_file, _sha

_NATIVE = ("word", "lo", "chrome")
_ROUTES = (
    "native", "p8_default", "p8_screen", "p8_nooutputfonts", "p8_ps_roundtrip",
    "p9_200", "p9_300", "p9_grain", "p10_200_heb", "p10_200_eng", "p10_grain_heb",
)


def _json(path: Path) -> dict:
    return json.loads(path.read_bytes())


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n",
                    encoding="utf-8")


def _tesseract_version() -> str:
    return subprocess.check_output(["tesseract", "--version"], text=True, timeout=30).splitlines()[0]


def _pins(tessdata: Path) -> dict:
    import pypdfium2 as pdfium

    if Path(os.environ.get("TESSDATA_PREFIX", "")).resolve() != tessdata.resolve():
        raise ValueError("TESSDATA_PREFIX must point to the directory supplied as --tessdata")
    if os.environ.get("OMP_THREAD_LIMIT") != "1":
        raise ValueError("Set OMP_THREAD_LIMIT=1 to bound the local Tesseract work")
    poppler = subprocess.run(["pdftotext", "-v"], check=True, capture_output=True, text=True, timeout=30)
    return {
        "ghostscript": producers.gs_version(),
        "tesseract": _tesseract_version(),
        "tessdata_sha256": {lang: _sha(tessdata/f"{lang}.traineddata") for lang in ("heb", "eng")},
        "img2pdf": imagepdf._version("img2pdf"),
        "pypdfium2": version("pypdfium2"),
        "pdfium": str(pdfium.PDFIUM_INFO),
        "Pillow": version("Pillow"),
        "numpy": version("numpy"),
        "pdfminer.six": version("pdfminer.six"),
        "pymupdf": version("PyMuPDF"),
        "poppler": (poppler.stderr or poppler.stdout).splitlines()[0],
    }


def _native_pdf(root: Path, entry: dict, row: dict) -> Path:
    doc_id, producer = row["doc_id"], row["producer"]
    if not re.fullmatch(r"(tender|report)-[0-9]+", doc_id) or producer not in _NATIVE:
        raise ValueError("Invalid native slot identity")
    result = _owned_file(root, entry["result"])
    tree = _owned_file(result.parent, f"{doc_id}.tree.json")
    plain = _owned_file(root, str(result.parent / producer / f"{doc_id}.{producer}.pdf"))
    for path, key in ((result, "producer_result_sha256"), (tree, "tree_sha256"), (plain, "plain_sha256")):
        if _sha(path) != row[key]:
            raise ValueError(f"Native audit pin failed: {doc_id}/{producer}/{key}")
    return plain


def _validate_slot(folder: Path, rows: list[dict], source: dict) -> None:
    if [row["route"] for row in rows] != list(_ROUTES[1:]):
        raise ValueError(f"Incomplete or unordered matrix slot: {folder.name}")
    for row in rows:
        if (row["doc_id"], row["native_producer"], row["native_version"], row["native_sha256"]) != (
            source["doc_id"], source["producer"], source["producer_version"], source["plain_sha256"]
        ):
            raise ValueError(f"Matrix slot lineage differs: {folder.name}")
        if _sha(_owned_file(folder, row["artifact"])) != row["pdf_sha256"]:
            raise ValueError(f"Matrix PDF changed: {folder.name}/{row['route']}")


def _render_slot(plain: Path, folder: Path, source: dict, pins: dict) -> list[dict]:
    recorded = []

    def add(route, receipt, parent):
        asset = receipt["outputs"]["pdf"]
        path = _owned_file(folder, asset["path"])
        audit = _counts(read_text_layer(path))
        if audit["pages"] != source["pages"]:
            raise ValueError(f"Page count differs: {source['doc_id']}/{route}")
        observed_version = receipt.get("version")
        if route.startswith("p8_") and observed_version != pins["ghostscript"]:
            raise producers.VersionChanged(f"Ghostscript differs at {route}")
        if route.startswith("p10_") and observed_version != pins["tesseract"]:
            raise producers.VersionChanged(f"Tesseract differs at {route}")
        if route.startswith("p9_"):
            expected = f"pypdfium2 + Pillow + {pins['img2pdf']}"
            if receipt["tool"] != expected:
                raise producers.VersionChanged(f"img2pdf differs at {route}")
        recorded.append({
            "doc_id": source["doc_id"], "native_producer": source["producer"],
            "native_version": source["producer_version"], "native_sha256": source["plain_sha256"],
            "route": route, "producer": receipt["producer"],
            "version": observed_version or {
                name: pins[name] for name in ("pypdfium2", "pdfium", "Pillow", "img2pdf", "numpy")
            },
            "options": receipt["options"], "input_sha256": receipt["input_sha256"],
            "parent_pdf_sha256": parent, "artifact": asset["path"], "pdf_sha256": asset["sha256"],
            **audit,
        })
        return asset["sha256"]

    source_sha = source["plain_sha256"]
    for variant in producers.GS_VARIANTS:
        route = f"p8_{variant}"
        add(route, producers.gs_redistil(plain, folder/f"{route}.pdf", variant), source_sha)

    seed = int(source["doc_id"].rsplit("-", 1)[1])
    grain_quality = random.Random(seed).randint(40, 70)
    with tempfile.TemporaryDirectory(dir=folder, prefix="jpeg-") as page_tmp:
        pages = Path(page_tmp)
        image_parents = {}
        for route, dpi, quality, grain in (("p9_200", 200, 85, 0.0), ("p9_300", 300, 85, 0.0),
                                           ("p9_grain", 200, grain_quality, 1.0)):
            image_parents[route] = add(
                route, imagepdf.rasterise(plain, folder/f"{route}.pdf", dpi, quality, grain, seed,
                                          keep_pages=pages/route if dpi == 200 else None), source_sha)
        for route, origin, lang in (("p10_200_heb", "p9_200", "heb"), ("p10_200_eng", "p9_200", "eng"),
                                    ("p10_grain_heb", "p9_grain", "heb")):
            jpgs = sorted((pages/origin).glob("*.jpg"))
            if len(jpgs) != source["pages"]:
                raise ValueError(f"Missing OCR input pages: {source['doc_id']}/{route}")
            add(route, imagepdf.ocr_layer(jpgs, folder/f"{route}.pdf", lang, 200), image_parents[origin])
    return recorded


def run(root: Path, native_audit: Path, output: Path, tessdata: Path, limit: int | None = None) -> dict:
    """Create or resume the matrix. Producer files live locally; report contains pins and counts."""
    root, output = root.resolve(), output.resolve()
    if output.is_relative_to(root):
        raise ValueError("Keep matrix outputs outside the saved source pilot")
    manifest_path = _owned_file(root, "manifest.json")
    manifest, native = _json(manifest_path), _json(native_audit)
    if (native["schema"] != "hdocsyngen_pilot_readback.v1"
            or _sha(manifest_path) != native["pilot_manifest_sha256"]
            or manifest["versions"] != manifest["versions_after"]
            or native["producer_versions"] != manifest["versions"]):
        raise ValueError("Native audit does not bind the exact completed pilot")
    entries = {entry["doc_id"]: entry for entry in manifest["docs"]}
    native_rows = native["rows"]
    keys = {(row["doc_id"], row["producer"]) for row in native_rows}
    if len(native_rows) != len(keys) or keys != {(doc, prod) for doc in entries for prod in _NATIVE}:
        raise ValueError("Native audit does not cover all three slots per tree")
    if limit is not None and limit < 1:
        raise ValueError("Slot limit must be positive")

    pins = _pins(tessdata)
    header = {"schema": "hdocsyngen_pilot_matrix.v1", "native_audit_sha256": _sha(native_audit),
              "pilot_manifest_sha256": native["pilot_manifest_sha256"], "tool_versions": pins,
              "native_reader_versions": native["reader_versions"],
              "routes": list(_ROUTES), "planned_producer_slots": len(native_rows),
              "recipe_sha256": sha256(Path(__file__).read_bytes()).hexdigest()}
    output.mkdir(parents=True, exist_ok=True)
    pin_file = output/"run-pins.json"
    if pin_file.exists():
        if _json(pin_file) != header:
            raise ValueError("Matrix source, tool versions, or recipe changed since the earlier run")
    else:
        _write(pin_file, header)

    rows = []
    for source in native_rows[:limit]:
        plain = _native_pdf(root, entries[source["doc_id"]], source)
        slot = output/f"{source['doc_id']}.{source['producer']}"
        if slot.is_symlink():
            raise ValueError(f"Unexpected matrix slot symlink: {slot.name}")
        if slot.exists():
            derivatives = _json(slot/"audit.json")["rows"]
            _validate_slot(slot, derivatives, source)
        else:
            with tempfile.TemporaryDirectory(dir=output, prefix=".slot-") as tmp:
                stage = Path(tmp)/"artifacts"
                stage.mkdir()
                derivatives = _render_slot(plain, stage, source, pins)
                _validate_slot(stage, derivatives, source)
                _write(stage/"audit.json", {"rows": derivatives})
                stage.rename(slot)
        native_row = {**source, "route": "native", "native_producer": source["producer"],
                      "native_version": source["producer_version"], "pdf_sha256": source["plain_sha256"]}
        rows.extend((native_row, *derivatives))
    if _pins(tessdata) != pins:
        raise producers.VersionChanged("Matrix reader or producer pin changed during the run")
    return {**header, "audited_producer_slots": len(rows)//len(_ROUTES), "rows": rows}
