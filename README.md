# hdocsyngen

Synthetic Hebrew documents with exact gold, rendered by **real producers** (Word, LibreOffice, Chrome, and later
Ghostscript, print-to-image and OCR layers). Part of [HeOCR](https://github.com/HeOCR).

**The idea:** generate a source tree, write it as DOCX (and later HTML, XLSX, PPTX), let real programs make the PDFs,
and prove that the gold survived each program. The gold is exact because we wrote the source. The design is
[hocrsyngen docs/document_generator_design.md](https://github.com/HeOCR/hocrsyngen/blob/main/docs/document_generator_design.md).

**Status:** pilot build. The producers, checks and pilot runner are in [docs/producers.md](docs/producers.md). This release contains:
- the source tree and its gold (`hdoc_tree.v1` and `hdoc_gold.v1`, owned and signed off by heocr-eval, see [docs/hdoc_tree_v1.md](docs/hdoc_tree_v1.md));
- Hebrew counting and the `model` numbering labels;
- generated values;
- the `tender`, `report` and `tables` templates (`tables`: see [docs/tables_forms_design.md](docs/tables_forms_design.md));
- a byte-reproducible DOCX writer;
- an independent DOCX reader;
- a DOCX gold check that also accepts producer-re-saved DOCX (numIds may be renumbered).

```bash
python -m pip install -e ".[test]"
python -m pytest
hdocsyngen build --template tender --seed 7 --count 3 --pool pool.jsonl --require-licence CC0-1.0 --out out/
hdocsyngen verify-docx out/tender-7.tree.json resaved/tender-7.docx
```

The [native producer pilot](docs/native_pilot.md) checks literal page text from Word, LibreOffice and Chrome.

For a source tree containing RTL tables or forms, `render-structure-geometry`
writes a native Chrome PDF and a JSON record of its printed structure. Install the
`fonts,pdf,readback` extras and use a folder of allow-listed font files.

```bash
hdocsyngen render-structure-geometry out/tables-7.tree.json --font-dir fonts --out out/tables-7-layout
```

The record carries logical `heocr_table.v1` gold, including header counts and
page breaks, plus printed cell rectangles in top-left PDF points. Repeated
headers and side-by-side copies refer back to their logical cells. A private
colour twin identifies even empty and borderless cells. The verifier checks
that it preserves every painted glyph position and checks cell text against
the original tree before accepting the geometry. Form records include
`hdoc_form.v1`, observed field pages and bounding boxes for their printed
parts. Embedded logical tables preserve the same continuation metadata.

**Text:**
- The pool is a JSONL file, `{"id", "text", "licence", "source"}`, chosen and decontaminated by the caller.
- Every document records the pool entries it used and their licences.
- The tests use invented sentences only (`tests/data/invented_pool.jsonl`).

**Licence:** the code is Apache-2.0. Generated output is CC0 only where all of its inputs are CC0.
