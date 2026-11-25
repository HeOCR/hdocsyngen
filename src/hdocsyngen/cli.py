"""hdocsyngen command line.

  hdocsyngen build --template tender --seed 7 --pool pool.jsonl --out out/   # tree, gold and DOCX for one or more seeds (templates: tender, report, tables, forms)
  hdocsyngen verify-docx tree.json file.docx                               # check a (producer-saved) DOCX against a tree
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import __version__
from .gold import gold
from .templates import TEMPLATES, build
from .textpool import TextPool
from .tree import dumps, loads, validate
from .verify import verify_docx
from .writers import docx


def cmd_build(a) -> int:
    pool = TextPool.load(a.pool, a.require_licence)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "hdocsyngen_build.v0", "hdocsyngen": __version__, "template": a.template,
                "require_licence": a.require_licence,
                "pool_sha256": hashlib.sha256(Path(a.pool).read_bytes()).hexdigest(), "docs": []}
    for i in range(a.count):
        seed = a.seed + i
        doc_id = f"{a.template}-{seed}"
        doc = build(a.template, doc_id, seed, pool)
        problems = validate(doc)
        if problems:
            print(f"{doc_id}: invalid tree: {problems[:3]}", file=sys.stderr)
            return 1
        data = docx.write(doc)
        vp = verify_docx(doc, data)
        if vp:
            print(f"{doc_id}: DOCX does not carry the gold: {vp[:3]}", file=sys.stderr)
            return 1
        tj = dumps(doc)
        files = {f"{doc_id}.tree.json": tj.encode(),
                 f"{doc_id}.gold.json": json.dumps(gold(doc, tj), ensure_ascii=False, indent=1).encode(),
                 f"{doc_id}.docx": data}
        for name, b in files.items():
            (out / name).write_bytes(b)
        manifest["docs"].append({"doc_id": doc_id, "seed": seed,
                                 "files": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}})
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"{a.count} documents in {out}")
    return 0


def cmd_verify_docx(a) -> int:
    doc = loads(Path(a.tree).read_text(encoding="utf-8"))
    problems = verify_docx(doc, Path(a.docx).read_bytes(), check_numbering=not a.no_numbering)
    for p in problems:
        print(p)
    print("ok" if not problems else f"{len(problems)} problems")
    return 0 if not problems else 1


def cmd_pdf_readback(a) -> int:
    from .pdfcheck import read_text_layer

    doc = loads(a.tree.read_text(encoding="utf-8")) if a.tree else None
    print(json.dumps(read_text_layer(a.pdf, doc, a.twin), indent=1))
    return 0


def cmd_pilot(a) -> int:
    from . import pilot
    spec = json.loads(Path(a.spec).read_text())
    man = pilot.run(spec, Path(a.out))
    print(f"{len(man['docs'])} documents in {a.out}")
    return 0


def cmd_pilot_summary(a) -> int:
    from . import pilot
    print(json.dumps(pilot.summary(Path(a.out)), ensure_ascii=False, indent=1))
    return 0


def cmd_pilot_readback(a) -> int:
    from .pilot_readback import run

    print(json.dumps(run(a.run), ensure_ascii=False, indent=1))
    return 0


def cmd_pilot_matrix(a) -> int:
    from .pilot_matrix import run

    print(json.dumps(run(a.run, a.native_audit, a.out, a.tessdata, a.limit), sort_keys=True,
                     separators=(",", ":")))
    return 0


def cmd_native_pilot(a) -> int:
    from .native_pilot import run

    result = run(a.trees, a.font_dir, a.out, a.layout_plan)
    print(json.dumps({key: result[key] for key in ("trees", "expected_slots", "verified_slots", "pages")}))
    return 1 if result["failures"] else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hdocsyngen")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--template", choices=TEMPLATES, required=True)
    b.add_argument("--seed", type=int, required=True)
    b.add_argument("--count", type=int, default=1)
    b.add_argument("--pool", required=True)
    b.add_argument("--require-licence", default=None, help="keep only pool entries with this licence, e.g. CC0-1.0")
    b.add_argument("--out", required=True)
    b.set_defaults(func=cmd_build)
    v = sub.add_parser("verify-docx")
    v.add_argument("tree")
    v.add_argument("docx")
    v.add_argument("--no-numbering", action="store_true", help="skip numPr checks (producers may restructure lists)")
    v.set_defaults(func=cmd_verify_docx)
    r = sub.add_parser("pdf-readback", help="audit a synthetic PDF text layer (needs the pdf and readback extras)")
    r.add_argument("pdf", type=Path)
    r.add_argument("--tree", type=Path, help="source tree for the LTR check (requires --twin)")
    r.add_argument("--twin", type=Path, help="colour twin for the LTR check (requires --tree)")
    r.set_defaults(func=cmd_pdf_readback)
    pl = sub.add_parser("pilot", help="run the pilot (needs the pdf, fonts and readback extras and the producers)")
    pl.add_argument("--spec", required=True)
    pl.add_argument("--out", required=True)
    pl.set_defaults(func=cmd_pilot)
    ps = sub.add_parser("pilot-summary")
    ps.add_argument("out")
    ps.set_defaults(func=cmd_pilot_summary)
    pr = sub.add_parser("pilot-readback", help="audit saved synthetic pilot PDFs without rerunning producers")
    pr.add_argument("run", type=Path, help="saved pilot directory")
    pr.set_defaults(func=cmd_pilot_readback)
    pm = sub.add_parser("pilot-matrix", help="run the implemented downstream routes on audited native PDFs")
    pm.add_argument("run", type=Path, help="saved pilot directory")
    pm.add_argument("--native-audit", type=Path, required=True, help="pilot-readback JSON for this pilot")
    pm.add_argument("--out", type=Path, required=True, help="local matrix artifacts and resumable slot receipts")
    pm.add_argument("--tessdata", type=Path, required=True, help="same directory as TESSDATA_PREFIX")
    pm.add_argument("--limit", type=int, help="only the first N native slots, for timing or smoke tests")
    pm.set_defaults(func=cmd_pilot_matrix)
    native = sub.add_parser("native-pilot", help="run Word, LibreOffice and Chrome with literal per-page GT")
    native.add_argument("--trees", type=Path, required=True, help="directory of approved source tree JSON files")
    native.add_argument("--font-dir", type=Path, action="append", required=True, help="open declared fonts")
    native.add_argument("--out", type=Path, required=True, help="new local output directory")
    native.add_argument("--layout-plan", type=Path,
                        help="JSON object mapping one-page tree IDs to the first left-column block ID or null")
    native.set_defaults(func=cmd_native_pilot)
    a = ap.parse_args(argv)
    if a.cmd == "pdf-readback" and (a.tree is None) != (a.twin is None):
        r.error("--tree and --twin must be supplied together")
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
