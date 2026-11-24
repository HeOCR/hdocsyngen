# Full implemented producer matrix

This extends the [four-reader native audit](pilot_v0_reader_audit.md) from
48 trees and three native producers to every downstream route used by the
pilot. The three native outputs per tree are Word for Mac, LibreOffice and
Chrome for Testing. P8, P9 and P10 are applied to each saved native PDF.
There are 144 producer slots. The archived LibreOffice TXT-export timeout
still has a two-page native PDF, so it can feed downstream routes. Its
native colour-twin check remains unavailable.

| Route from each native PDF | PDFs | Pages | PDFs with no PDFium visual characters |
| --- | ---: | ---: | ---: |
| Native (Word, LibreOffice, Chrome) | 144 | 473 | 0 |
| P8 Ghostscript default | 144 | 473 | 0 |
| P8 Ghostscript screen | 144 | 473 | 0 |
| P8 Ghostscript outlines | 144 | 473 | 144 |
| P8 PostScript round trip | 144 | 473 | 0 |
| P9 image-only, 200 dpi | 144 | 473 | 144 |
| P9 image-only, 300 dpi | 144 | 473 | 144 |
| P9 image-only, grain at 200 dpi | 144 | 473 | 144 |
| P10 Hebrew, clean 200 dpi | 144 | 473 | 0 |
| P10 English, clean 200 dpi | 144 | 473 | 0 |
| P10 Hebrew, grain at 200 dpi | 144 | 473 | 0 |
| **Total** | **1,584** | **5,203** | **576** |

The verifier is the same as in the native audit. PDFium glyphs are placed
in physical order. pdfminer, Poppler and PyMuPDF report their character
inventory and emitted sequence relative to those positions. A comparison
with a different inventory is reported separately from a sequence
difference. Native rows carry the colour-twin checks already recorded in
the native audit. The derivative rows are four-reader page diagnostics.

P8 converts the native PDF through four Ghostscript settings. P9 wraps
image-only 200 and 300 dpi versions and one seeded 200 dpi grain version
with the original JPEG quality range. P10 uses Tesseract's PDF layers with
Hebrew or English on the clean 200 dpi input and Hebrew on the grain input.
The language-data hashes, executable versions, route options and PDF
parent hashes are in the audit. A P10 input hash binds the ordered JPEG
bytes given to Tesseract; the parent PDF hash identifies the matching P9
wrap.

The matrix covers all implemented pilot routes. Windows Word, Pages,
Keynote/Numbers, Google Docs, WeasyPrint, Typst and the distinct macOS
Quartz print route are outside this run. Word for Mac's native export is
included. The OCR routes use the pilot's Tesseract PDF renderer. These
results describe synthetic PDF text layers for diagnosis.

In this run, the PDFium visual-character count matched the native PDF on 138 of 144 default and 138 of 144 screen outputs, and on 43 of 144 PostScript round trips. A count match alone does not establish character identity or reading order. PDFium and Poppler both returned no characters on 12 of 473 grain-plus-Hebrew OCR pages.

## Audit files

- [Full matrix evidence](pilot_full_matrix.json.gz), gzipped UTF-8 JSON.
  SHA-256 `1c07a2b29053f444acef44707eb3bdce09c33e3001fd63701464630e580be0e9`.
- Uncompressed report SHA-256 `53212ea0063806dbbb110d44daec1a17acd84ac5ed0b77575b4acd6825736b2f`.
- [Runner and dependencies](producers.md#scaling-the-saved-producer-matrix).
  On the completed output directory the same command verifies every
  derivative hash before emitting the report again.
  A fresh Ghostscript run can assign different font subset tags, so the
  derivative hashes bind the recorded files.

The original report and audit evidence are dedicated under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). The public
files contain counts, versions and hashes. Producer documents, fonts and
extracted text stay outside this repository.
