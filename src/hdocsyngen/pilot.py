"""The pilot run (design note §9): trees × Word for Mac, LibreOffice and Chrome, plus print-to-image and OCR layers.

`run(spec, out)` writes, per document, the tree, the gold, the DOCX and HTML (plain and colour twin), every producer
output, and a result record (producer records, DOCX checks, PDF checks, census, producer labels). `summary(out)`
aggregates the records for the pilot report. Word's version is checked before and after the run and per document;
a change aborts the run (`producers.VersionChanged`).

Spec (JSON): {"seed_base": int, "templates": {"tender": 24, "report": 24}, "pool": path, "require_licence":
"CC0-1.0", "fonts_dirs": [...], "producers": ["word", "lo", "chrome"], "image_sample": 12, "grain_sample": 12}
"""
from __future__ import annotations

import hashlib
import json
import random
import traceback
from collections import Counter, defaultdict
from pathlib import Path

from . import __version__
from . import fonts as F
from . import imagepdf as I
from . import pdfcheck as C
from . import producers as P
from .gold import gold
from .labels import producer_labels, read_export
from .numbering import model_labels
from .templates import build
from .textpool import TextPool
from .tree import dumps, validate
from .verify import verify_docx
from .writers import docx as DOCX
from .writers import html as HTML


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


BULLETS = {"•", "–", "-", "*", "◦", "▪", "·"}


def _label_diffs(doc, producer: dict[str, str]) -> dict:
    model = model_labels(doc)
    out = Counter()
    for pid, m in model.items():
        if pid not in producer:
            out["unmatched"] += 1
        elif m.strip() != producer[pid].strip():
            # LibreOffice's text export writes every bullet as U+2022, whatever the PDF draws: bullets agree as a class.
            if m.strip() in BULLETS and producer[pid].strip() in BULLETS:
                out["same_bullet_class"] += 1
            else:
                out["differ"] += 1
        else:
            out["same"] += 1
    return dict(out)


def producer_gold(g: dict, producer: str, r: dict, pdf_name: str) -> dict:
    """The gold for one producer's PDF: the tree gold plus the observed layers (design note §3.2): `label_producer`
    (the scored reference, eval), the pages of every block, `not_rendered`, and the twin's geometry shift."""
    import copy
    out = copy.deepcopy(g)
    out["producer"] = {"name": producer, "pdf": pdf_name, "version": r["plain"]["version"],
                       "pdf_sha256": r["plain"]["outputs"]["pdf"]["sha256"]}
    labels = r.get("labels")
    out["label_basis"] = "producer" if labels is not None else "model"
    checks = r["pdf_check"]["blocks"]
    moved = r["pdf_check"].get("moved_blocks", {})
    for b in out["blocks"]:
        c = checks.get(b["id"])
        if c is not None:
            b["pages"] = c["pages"]
            if c.get("not_rendered"):
                b["not_rendered"] = True
            if b["id"] in moved:
                b["twin_shift_pt"] = moved[b["id"]]
        if labels is not None and "label_model" in b:
            b["label_producer"] = labels.get(b["id"])
    pv = r["pdf_check"].get("page_values", {})
    for kind in ("header", "footer"):
        for f in out["furniture"][kind]:
            c = checks.get(f["id"])
            if c is not None:
                f["pages"] = c["pages"]
            if f.get("fields"):
                f["page_values"] = [{"page": v["page"], "field_offset": v["field_offset"], "text": v["text"]}
                                    for v in pv.get(f["id"], [])]
    out["checks"] = {"twin_geometry": {"match": "order-free, same page and character",
                                       "shift_recorded_over_pt": 0.25, "fail_over_pt": 3.0},
                     "label_comparison": "exact after stripping; bullet glyphs equal any bullet (a class)",
                     "fonts": "hard: every PDF font is a PostScript name of the requested open family"}
    return out


def run_doc(template: str, seed: int, pool: TextPool, reg: F.Registry, out: Path, producers: list[str],
            image: bool, grain: bool) -> dict:
    doc_id = f"{template}-{seed}"
    d = out / doc_id
    d.mkdir(parents=True, exist_ok=True)
    doc = build(template, doc_id, seed, pool)
    font_files = F.fit_font(doc, reg, random.Random(seed))
    problems = validate(doc)
    if problems:
        return {"doc_id": doc_id, "error": f"invalid tree: {problems[:3]}"}
    allowed = reg.postscript_names(doc.meta.font)
    tj = dumps(doc)
    gold_doc = gold(doc, tj)
    files = {"tree.json": tj.encode(), "gold.json": json.dumps(gold_doc, ensure_ascii=False, indent=1).encode(),
             "docx": DOCX.write(doc), "twin.docx": DOCX.write(doc, twin=True),
             "html": HTML.write(doc), "twin.html": HTML.write(doc, twin=True)}
    for name, b in files.items():
        (d / f"{doc_id}.{name}").write_bytes(b)
    rec = {"doc_id": doc_id, "template": template, "seed": seed, "font": doc.meta.font, "font_files": font_files,
           "sources": {n: _sha(b) for n, b in files.items()}, "docx_self_check": verify_docx(doc, files["docx"]),
           "producers": {}}
    plain_docx, twin_docx = d / f"{doc_id}.docx", d / f"{doc_id}.twin.docx"
    plain_html, twin_html = d / f"{doc_id}.html", d / f"{doc_id}.twin.html"
    for prod in producers:
        r: dict = {}
        try:
            if prod == "word":
                r["plain"] = P.word_convert(plain_docx, d / "word")
                r["twin"] = P.word_convert(twin_docx, d / "word", outputs=("pdf",))
                plain_pdf, twin_pdf = d / "word" / f"{doc_id}.word.pdf", d / "word" / f"{doc_id}.twin.word.pdf"
                resaved = d / "word" / f"{doc_id}.word.docx"
                labels, unmatched = producer_labels(doc, read_export(d / "word" / f"{doc_id}.word.labels.tsv"))
            elif prod == "lo":
                r["plain"] = P.lo_convert(plain_docx, d / "lo")
                r["twin"] = P.lo_convert(twin_docx, d / "lo", outputs=("pdf",))
                plain_pdf, twin_pdf = d / "lo" / f"{doc_id}.lo.pdf", d / "lo" / f"{doc_id}.twin.lo.pdf"
                resaved = d / "lo" / f"{doc_id}.lo.docx"
                labels, unmatched = producer_labels(doc, read_export(d / "lo" / f"{doc_id}.lo.txt"))
            elif prod == "chrome":
                r["plain"] = P.chrome_convert(plain_html, d / "chrome")
                r["twin"] = P.chrome_convert(twin_html, d / "chrome")
                plain_pdf, twin_pdf = d / "chrome" / f"{doc_id}.chrome.pdf", d / "chrome" / f"{doc_id}.twin.chrome.pdf"
                resaved, labels, unmatched = None, None, None
            else:
                raise ValueError(prod)
            if resaved is not None:
                r["resaved_docx_check"] = verify_docx(doc, resaved.read_bytes())
            if labels is not None:
                r["labels"] = labels
                r["label_agreement"] = _label_diffs(doc, labels)
            r["pdf_check"] = C.verify_pdf(doc, plain_pdf, twin_pdf, allowed)
            r["census"] = C.census(plain_pdf)
            pg = producer_gold(gold_doc, prod, r, plain_pdf.name)
            (d / f"{doc_id}.{prod}.gold.json").write_text(json.dumps(pg, ensure_ascii=False, indent=1))
            if image:
                for dpi in (200, 300):
                    ip = d / prod / f"{doc_id}.{prod}.img{dpi}.pdf"
                    pages = d / prod / f"pages{dpi}"
                    r[f"img{dpi}"] = I.rasterise(plain_pdf, ip, dpi, 85, 0.0, seed, keep_pages=pages)
                    if dpi == 200:
                        jpgs = sorted(pages.glob("*.jpg"))
                        for lang in ("heb", "eng"):
                            op = d / prod / f"{doc_id}.{prod}.img200.ocr_{lang}.pdf"
                            r[f"ocr_{lang}"] = I.ocr_layer(jpgs, op, lang, 200)
                            r[f"ocr_{lang}"]["census"] = C.census(op)
            if grain:
                q = random.Random(seed).randint(40, 70)
                gp = d / prod / f"{doc_id}.{prod}.grain200q{q}.pdf"
                r["grain"] = I.rasterise(plain_pdf, gp, 200, q, 1.0, seed)
        except P.VersionChanged:
            raise
        except Exception as e:                                   # a producer failure is a result, not a crash
            r["error"] = f"{type(e).__name__}: {e}"
            r["traceback"] = traceback.format_exc(limit=3)
        rec["producers"][prod] = r
    (d / f"{doc_id}.result.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    return rec


def run(spec: dict, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    pool_sha = _sha(Path(spec["pool"]).read_bytes())
    if spec.get("pool_sha256") and spec["pool_sha256"] != pool_sha:
        raise ValueError(f"pool sha256 {pool_sha} is not the pinned {spec['pool_sha256']}")
    pool = TextPool.load(spec["pool"], spec.get("require_licence"))
    reg = F.Registry.scan([Path(p).expanduser() for p in spec["fonts_dirs"]])
    producers = spec.get("producers", ["word", "lo", "chrome"])
    versions0 = {"word": P.word_version() if "word" in producers else None,
                 "lo": P.lo_version() if "lo" in producers else None,
                 "chrome": P.chrome_version() if "chrome" in producers else None}
    manifest = {"schema": "hdocsyngen_pilot.v0", "hdocsyngen": __version__, "spec": spec,
                "pool_sha256": pool_sha, "versions": versions0,
                "fonts": [{"family": f.family, "file": Path(f.path).name, "postscript": f.postscript,
                           "sha256": f.sha256, "licence": F.OPEN_FAMILIES[f.family]} for f in reg.files],
                "docs": []}
    n = 0
    for template, count in spec["templates"].items():
        for i in range(count):
            seed = spec["seed_base"] + (0 if template == "tender" else 100_000) + i
            rec = run_doc(template, seed, pool, reg, out, producers, image=n < spec.get("image_sample", 0),
                          grain=n < spec.get("grain_sample", 0))
            manifest["docs"].append({"doc_id": rec["doc_id"], "result": f"{rec['doc_id']}/{rec['doc_id']}.result.json"})
            n += 1
            (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    versions1 = {k: (getattr(P, f"{k}_version")() if v else None) for k, v in
                 {"word": versions0["word"], "lo": versions0["lo"], "chrome": versions0["chrome"]}.items()}
    if versions1 != versions0:
        raise P.VersionChanged(f"{versions0} -> {versions1}")
    manifest["versions_after"] = versions1
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    return manifest


def summary(out: Path) -> dict:
    man = json.loads((out / "manifest.json").read_text())
    agg: dict = defaultdict(lambda: defaultdict(Counter))
    for entry in man["docs"]:
        rec = json.loads((out / entry["result"]).read_text())
        for prod, r in rec.get("producers", {}).items():
            a = agg[prod]
            a["docs"]["n"] += 1
            if "error" in r:
                a["docs"]["error"] += 1
                continue
            pc = r["pdf_check"]
            a["docs"]["gold_ok"] += int(not pc["problems"])
            a["docs"]["font_fail"] += int(any("font" in p for p in pc["problems"]))
            a["docs"]["geometry_fail"] += int(any("geometry" in p for p in pc["problems"]))
            a["docs"]["text_fail"] += int(any("characters not in" in p for p in pc["problems"]))
            a["blocks"]["not_rendered"] += len(pc["not_rendered"])
            if "resaved_docx_check" in r:
                a["docs"]["resaved_docx_ok"] += int(not r["resaved_docx_check"])
            for k, v in r.get("label_agreement", {}).items():
                a["labels"][k] += v
            for pg in r["census"]["pages"]:
                c = a["pages"]
                c["n"] += 1
                c["t2_signal_ge_0.5"] += int(pg["t2_signal"] >= 0.5)
                c["type3"] += int(pg["type3_fonts"] > 0)
                c["font_without_tounicode"] += int(pg["fonts_without_tounicode"] > 0)
                c["pua"] += int(pg["pua_share"] > 0)
                c["single_glyph_runs_majority"] += int(pg["single_glyph_runs_share"] > 0.5)
            a["census"][f"producer={r['census']['producer']}"] += 1
            a["census"][f"struct_tree={r['census']['struct_tree']}"] += 1
            for lang in ("heb", "eng"):
                if f"ocr_{lang}" in r:
                    for pg in r[f"ocr_{lang}"]["census"]["pages"]:
                        a[f"ocr_{lang}_pages"]["n"] += 1
                        a[f"ocr_{lang}_pages"]["t2_signal_ge_0.5"] += int(pg["t2_signal"] >= 0.5)
    return {"pilot": man["spec"], "versions": man["versions"], "by_producer": {p: {k: dict(v) for k, v in a.items()}
                                                                                for p, a in agg.items()}}
