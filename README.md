# hdocsyngen

Synthetic Hebrew documents with exact gold, rendered by **real producers** (Word, LibreOffice, Chrome, and later
Ghostscript, print-to-image and OCR layers). Part of [HeOCR](https://github.com/HeOCR).

**The idea:** generate a source tree, write it as DOCX (and later HTML, XLSX, PPTX), let real programs make the PDFs,
and prove that the gold survived each program. The gold is exact because we wrote the source. The design is
[hocrsyngen docs/document_generator_design.md](https://github.com/HeOCR/hocrsyngen/blob/main/docs/document_generator_design.md).

**Status:** pilot build. The producers, checks and pilot runner are in [docs/producers.md](docs/producers.md). This release contains:
- the source tree and its gold (`hdoc_tree.v1`, a **draft** owned by heocr-eval, see [docs/hdoc_tree_v1.md](docs/hdoc_tree_v1.md));
- Hebrew counting and the `model` numbering labels;
- generated values;
- the `tender` and `report` templates;
- a byte-reproducible DOCX writer;
- an independent DOCX reader;
- a DOCX gold check that also accepts producer-re-saved DOCX (numIds may be renumbered).

```bash
python -m pip install -e ".[test]"
python -m pytest
hdocsyngen build --template tender --seed 7 --count 3 --pool pool.jsonl --require-licence CC0-1.0 --out out/
hdocsyngen verify-docx out/tender-7.tree.json resaved/tender-7.docx
```

**Text:**
- The pool is a JSONL file, `{"id", "text", "licence", "source"}`, chosen and decontaminated by the caller.
- Every document records the pool entries it used and their licences.
- The tests use invented sentences only (`tests/data/invented_pool.jsonl`).

**Licence:** the code is Apache-2.0. Generated output is CC0 only where all of its inputs are CC0.
