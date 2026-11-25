# Native producer matrix follow-up

The producer follow-up to [hdocsyngen #2](https://github.com/HeOCR/hdocsyngen/pull/2)
tested 24 tender and 24 report trees. This local run used newly authored
CC0 Hebrew and only the open Alef family. In a separate two-tree smoke,
LibreOffice substituted Helvetica for a David Libre run containing an
underscore or at sign. The Alef scope passed with the same font check.

| Producer | PDF pairs passing gold checks | Plain pages | Re-saved DOCX passing |
| --- | ---: | ---: | ---: |
| Word for Mac 16.115.2 | 48/48 | 152 | 48/48 |
| LibreOffice 26.2.5.2 | 48/48 | 150 | 48/48 |
| Chrome for Testing 158.0.8127.36 | 48/48 | 143 | — |

The [matrix receipt](producer_matrix_train_pilot.json) records per-document
producer versions, including Word bundle build `16.115.26112215`, and the
plain and colour-twin PDF hashes. The separate replay compared four readers on all 144 plain PDFs and used
the colour twins to verify LTR token positions. All 192 source DOCX/HTML variants
reproduced byte-for-byte. The six visual spot checks used the first tender and
first report across the three producers.

One LibreOffice report hit the TXT export timeout. The scoped retry used
byte-identical DOCX and twin inputs. Its PDF, twin and re-saved DOCX verified,
and the TXT export timed out again. Its numbering remains model-basis, with
the missing producer-label comparison recorded in the receipt.

This is a TRAIN-only engineering pilot. A digest-only spot check flagged
short or whole-line matches in the rendered trees. The pilot artifacts remain
local under a TRAIN intake hold pending exact CLEAN. The report records
producer checks and no OCR accuracy.

## Screened rerun

The independent TRAIN CLEAN held all 48 trees in the first pilot. The pilot now accepts a
`protected_projections` object containing an absolute local `manifest` path
and its `sha256`. The manifest uses `hdocsyngen.pilot_projections.v1` and pins
`helpers` (the local `ph1keys.py` path and SHA-256), `normalizer_sha256`, and
`layers`. Each layer has a relative `path`, `sha256` and `rows`. Supply
newline-delimited hex digests for `short_whole_line` and
`unicode_whole_line`. The `normalized_whole_line` and `six_word` layers
are optional. Keep the projection files and helper local.

The filter regenerates matching text before writing DOCX or HTML. Tender
numbers are drawn as linked quantities, prices and subtotals, and the total
is recalculated. A matching tree is rejected and rebuilt with the next
deterministic seed. To carry a prior LibreOffice TXT hold, list its original
slot ID in the pilot spec's `hold_lo_labels`. The new tree assigned to that
slot retains model-basis numbering.

After the native run, replay each PDF pair with the same projection:

```sh
hdocsyngen pilot-physical-lines /local/screened-pilot \
  --out /local/new-private-line-sidecars > /local/physical-lines-receipt.json
```

The replay reads the plain PDF's glyph positions and uses its colour twin
to identify the source block for each glyph. The line text comes from the
tree's logical span, with page fields and visible list and note marks
checked against the glyphs. It records the one-based page and order,
source span, plain PDF bounding box in bottom-left PDF points, and text
and PDF digests. A wrapped cell is represented by its individual source
spans. The line sidecar is separate from `hdoc_gold.v1`, and a PDF label
observed here does not upgrade LibreOffice's model-basis label status.

A source or position mismatch and any protected physical-line match hold
the entire tree across Word, LibreOffice and Chrome. Send the receipt and
line-sidecar pins for independent CLEAN. An expansion requires its signed
allowlist.

The screened Chrome route places the note's visible marker on the same line
as the note text. The plain and twin writers use the same setting.
