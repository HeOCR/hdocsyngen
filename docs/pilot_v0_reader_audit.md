# Pilot v0: four-reader PDF audit

This is an offline replay of the [48-tree pilot](pilot_v0_report.md). The
[per-document record](pilot_v0_reader_audit.json) covers all 144 original
producer slots. It binds every source tree, producer result and PDF by
SHA-256 and records the producer version and its evidence for each slot.

| Producer | Version | Plain PDFs | Pages | Colour twins |
| --- | --- | ---: | ---: | ---: |
| Word for Mac | 16.115 | 48 | 158 | 48 |
| LibreOffice | 26.2.5.2 | 48 | 155 | 47 |
| Chrome for Testing | 158.0.8127.36 | 48 | 160 | 48 |

For 143 slots, both PDF hashes and both versions matched the per-document
producer receipts. LibreOffice's text export timed out on
`report-20361126` after writing its two-page PDF. The PDF's metadata agrees
with the pinned run release. That slot has a plain-page comparison and no
colour-twin token comparison. The earlier export failure remains recorded.

## What the readers showed

PDFium positions are ordered by horizontal baseline and by increasing x
within each line. The comparison readers emit pdfminer content-stream order,
Poppler `pdftotext -raw` order and PyMuPDF `get_text(sort=False)` order. The
comparison decomposes compatibility characters, groups mirrored brackets
and removes whitespace and bidi control characters.

Each of the three readers differed from the PDFium position-sorted sequence
on all **464 pages** where their normalized character inventories matched.
On **nine Chrome pages**, each reader returned **219 additional characters
in total** relative to PDFium. The audit reports those pages as different
inventories. Sequence disagreement is a reader-order observation since
PDFium's physical order is one reference and the tree is the text gold.

Across the 143 paired slots, the colour twins carried **6,416 forward LTR
tokens**, **zero detected reversals** and **15 unresolved tokens**. The
single-line BiDi comparisons and the unresolved counts are preserved per
document. These checks diagnose synthetic PDF text layers.

## Reproduce

Install the project with `pip install -e ".[pdf,readback]"` and add Poppler's
`pdftotext` to PATH. Given the original saved synthetic pilot directory:

```sh
hdocsyngen pilot-readback /path/to/pilot-v0 > audit.json
```

The command checks the saved receipts and uses the saved PDFs. It runs
without starting Word, LibreOffice or Chrome. The JSON records every reader
version. The public audit JSON and this report are dedicated under
[CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/).
The manifest contains counts and pins. The source texts, PDFs and fonts
remain in their existing custody.
