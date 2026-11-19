"""hdocsyngen command line.

  hdocsyngen build --template tender --seed 7 --pool pool.jsonl --out out/   # tree, gold and DOCX for one or more seeds
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
    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
