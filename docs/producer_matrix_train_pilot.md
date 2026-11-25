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
